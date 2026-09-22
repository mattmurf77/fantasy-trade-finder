"""Pure offline outcomes for scorecard-spec §2; no database or serving imports.

The caller supplies immutable, exact-concept-bound evidence, not live records.
Timestamps are timezone-aware ISO 8601 strings or datetimes. Intervals are
half-open: interest at expiry cannot create a match. Missing identities or
ambiguous event ordering raise ValueError; the cohort reducer quarantines such
episodes while retaining every enrolled manager-league in its denominator.

Required episode fields: episode_id, concept_id, participants (two canonical
manager IDs), generated_at, start_at (first verified exposure), expires_at,
origin, observation, followup, events. Origin contains cohort_id, manager_id,
league_id, request_id, assignment_arm, model_id, model_version, selected_source
(nullable), and generating_sources. Followup contains post_milestone_seconds,
completion_seconds, ingestion_lag_seconds. Observation contains nullable
complete_through, post_milestone_complete_through, completion_complete_through
and boolean completion_supported. Each event contains event_id, concept_id,
at, type, and actor_id for actor actions. A view needs verified=True; a
completion needs verified=True and provider_transaction_id. Undo names a
target_event_id. Simultaneous decisions by one actor require unique sequence
numbers; ingestion/list order never decides their meaning.

Required cohort fields: cohort_id, eligibility_rule, frozen_at, window_start,
window_end, followup, members. Each member contains manager_id, league_id,
cluster_id, assigned_at, assignment_arm, request_count, observation_complete.
Membership is already eligibility-filtered *before* assignment. Request counts
include empty/error intents but exclude polling/retries. Optional guardrails
contain preregistration_id and caller-ratified limits; absence is unratified.
This module never grades private willingness or makes a promotion decision.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from itertools import groupby
import hashlib
import json
import math


VERSION = "scorecard-outcomes-v1"
EPISODE_SECONDS = 14 * 86400
_POSITIVE = {"like", "queue", "send"}
_DECISION = _POSITIVE | {"pass"}
_ACTOR = _DECISION | {"view", "undo", "withdraw", "reject", "confirm"}
_TERMINAL = {"invalidate", "cancel", "reject", "expire"}
_KNOWN = _ACTOR | _TERMINAL | {"complete", "delivered", "redisplay"}


def _time(value, field):
    try:
        result = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{field}: timezone-aware timestamp required") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{field}: timezone-aware timestamp required")
    return result.astimezone(timezone.utc)


def _iso(value):
    return value.isoformat().replace("+00:00", "Z") if value is not None else None


def _id(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}: nonempty identity required")
    return value


def _seconds(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{field}: finite nonnegative seconds required")
    return value


def _followup(value):
    if not isinstance(value, dict):
        raise ValueError("followup: explicit preregistered horizons required")
    return {key: _seconds(value.get(key), key) for key in (
        "post_milestone_seconds", "completion_seconds", "ingestion_lag_seconds")}


def _ratio(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def reduce_episode(episode, cutoff):
    """Reduce a frozen episode without mutating input or reading a wall clock."""
    cutoff = _time(cutoff, "cutoff")
    episode_id = _id(episode.get("episode_id"), "episode_id")
    concept = _id(episode.get("concept_id"), "concept_id")
    participants = episode.get("participants")
    if not isinstance(participants, list) or len(participants) != 2:
        raise ValueError("participants: exactly two canonical manager IDs required")
    participants = sorted(_id(p, "participant") for p in participants)
    if participants[0] == participants[1]:
        raise ValueError("participants: identities must differ")
    start = _time(episode.get("start_at"), "start_at")
    expiry = _time(episode.get("expires_at"), "expires_at")
    generated = _time(episode.get("generated_at"), "generated_at")
    if generated > start or expiry <= start or cutoff < start:
        raise ValueError("episode: require generation <= start <= cutoff and expiry > start")
    deadline = min(expiry, start + timedelta(seconds=EPISODE_SECONDS))
    origin = deepcopy(episode.get("origin"))
    if not isinstance(origin, dict):
        raise ValueError("origin: frozen origin required")
    for key in ("cohort_id", "manager_id", "league_id", "request_id", "assignment_arm", "model_id", "model_version"):
        _id(origin.get(key), f"origin.{key}")
    if origin["manager_id"] not in participants:
        raise ValueError("origin manager must be a participant")
    selected = origin.get("selected_source")
    sources = origin.get("generating_sources")
    if not isinstance(sources, list):
        raise ValueError("origin.generating_sources: explicit list required")
    sources = sorted(set(_id(s, "generating_source") for s in sources))
    if selected is not None:
        _id(selected, "selected_source")
        if selected not in sources:
            raise ValueError("selected_source must belong to generating_sources")
    origin["generating_sources"] = sources
    followup = _followup(episode.get("followup"))
    observation = episode.get("observation")
    if not isinstance(observation, dict) or not isinstance(observation.get("completion_supported"), bool):
        raise ValueError("observation: explicit completion_supported boolean required")
    observed = {key: _time(observation[key], key) if observation.get(key) is not None else None
                for key in ("complete_through", "post_milestone_complete_through", "completion_complete_through")}
    events = episode.get("events")
    if not isinstance(events, list):
        raise ValueError("events: list required")
    unique = {}
    for event in events:
        event = deepcopy(event)
        event_id = _id(event.get("event_id"), "event_id")
        at = _time(event.get("at"), f"event {event_id}.at")
        event["at"] = _iso(at)
        if event.get("concept_id") != concept:
            raise ValueError(f"event {event_id}: exact concept mismatch")
        kind = event.get("type")
        if kind not in _KNOWN:
            raise ValueError(f"event {event_id}: unknown type {kind!r}")
        if kind in _ACTOR and event.get("actor_id") not in participants:
            raise ValueError(f"event {event_id}: unknown actor")
        if at < start and kind not in {"delivered", "redisplay"}:
            raise ValueError(f"event {event_id}: predates frozen start")
        if "sequence" in event and (isinstance(event["sequence"], bool) or not isinstance(event["sequence"], int)):
            raise ValueError("sequence must be an integer")
        if event_id in unique and unique[event_id] != event:
            raise ValueError(f"event {event_id}: conflicting duplicate")
        unique[event_id] = event
    # ISO strings are normalized to UTC, but optional fractional seconds sort
    # lexically before a whole second's Z; use datetime for temporal ordering.
    ordered = sorted(unique.values(), key=lambda e: (_time(e["at"], "at"), e.get("sequence", 0), e["event_id"]))
    exposure = {p: None for p in participants}
    exposure_sources = set()
    for event in ordered:
        if _time(event["at"], "at") > cutoff:
            continue
        qualified = event["type"] == "view" and event.get("verified") is True
        fallback = (episode.get("allow_action_exposure") is True and event["type"] in _DECISION
                    and event.get("exposure_qualified") is True and event.get("evidence_class") == "validated_action")
        if qualified or fallback:
            actor = event["actor_id"]
            exposure[actor] = exposure[actor] or _time(event["at"], "at")
        if event.get("source"):
            exposure_sources.add(_id(event["source"], "event.source"))
    starts = [at for at in exposure.values() if at is not None]
    if not starts or min(starts) != start:
        raise ValueError("start_at must equal first verified exposure; redisplay cannot reset it")

    stacks = {p: [] for p in participants}
    active = {p: False for p in participants}
    intervals = {p: [] for p in participants}
    first_interest = {p: None for p in participants}
    decisions = {p: None for p in participants}
    orphan_actions = []
    reversals = []
    validity_attrition = []
    stale_after_completion = []
    confirmations = {p: [] for p in participants}
    completions = []
    send_times = []
    milestone = None
    terminal_at = deadline
    terminal_reason = "expired"
    undone = set()
    seen_decisions = {}

    for at, group in groupby(ordered, key=lambda e: _time(e["at"], "at")):
        if at > cutoff:
            break
        batch = list(group)
        for actor in participants:
            actions = [e for e in batch if e.get("actor_id") == actor and e["type"] in (_DECISION | {"undo", "withdraw"})]
            if len(actions) > 1 and (any("sequence" not in e for e in actions)
                                      or len({e["sequence"] for e in actions}) != len(actions)):
                raise ValueError("simultaneous actor decisions require unique sequence values")
        before = dict(active)
        # Closure wins at a timestamp boundary; identifier/list ordering cannot
        # create a zero-duration match against a simultaneous cancellation.
        closures = sorted(e["type"] for e in batch if e["type"] in _TERMINAL)
        completion_in_batch = any(e["type"] == "complete" and e.get("verified") is True and e.get("provider_transaction_id") for e in batch)
        if completion_in_batch:
            closures.insert(0, "completed")
        if closures and at < terminal_at:
            terminal_at, terminal_reason = at, closures[0]
        for event in batch:
            kind, actor = event["type"], event.get("actor_id")
            if kind == "send":
                send_times.append(at)
            if kind == "complete":
                if event.get("verified") is True and event.get("provider_transaction_id"):
                    _id(event["provider_transaction_id"], "provider_transaction_id")
                    completions.append(at)
                continue
            if kind == "confirm":
                confirmations[actor].append(at)
                continue
            if (completions or completion_in_batch) and kind in _DECISION | {"undo", "withdraw", "reject", "cancel"}:
                # This exact package has already executed. A later interaction
                # can be stale UI or inconsistent ingestion, not a reliable
                # reversal of an unexecuted offer. Keep the evidence visible.
                stale_after_completion.append({"at": _iso(at), "type": kind, "event_id": event["event_id"]})
                continue
            if milestone is not None and at >= milestone:
                if kind in {"invalidate", "expire"}:
                    validity_attrition.append({"at": _iso(at), "type": kind, "event_id": event["event_id"]})
                elif kind in {"withdraw", "pass", "reject", "cancel"}:
                    reversals.append({"at": _iso(at), "type": kind, "event_id": event["event_id"]})
            if kind not in _DECISION | {"undo", "withdraw"} or at >= min(deadline, terminal_at):
                continue
            if exposure[actor] is None or exposure[actor] > at:
                orphan_actions.append(event["event_id"])
                continue
            positive_before = active[actor]
            if kind in _DECISION:
                seen_decisions[event["event_id"]] = event
                stacks[actor].append(event)
            elif kind == "withdraw":
                stacks[actor] = []
            else:
                target = event.get("target_event_id")
                prior = seen_decisions.get(target)
                if prior is None or prior["actor_id"] != actor:
                    raise ValueError(f"undo {event['event_id']}: unknown or wrong-actor target")
                undone.add(target)
                stacks[actor] = [item for item in stacks[actor] if item["event_id"] not in undone]
            decisions[actor] = stacks[actor][-1]["type"] if stacks[actor] else None
            active[actor] = decisions[actor] in _POSITIVE
            if kind == "undo" and milestone is not None and positive_before and not active[actor]:
                reversals.append({"at": _iso(at), "type": kind, "event_id": event["event_id"]})
        valid = at < terminal_at
        for actor in participants:
            active[actor] = active[actor] and valid
            if before[actor] and not active[actor]:
                intervals[actor][-1]["end"] = _iso(min(at, terminal_at))
            elif active[actor] and not before[actor]:
                intervals[actor].append({"start": _iso(at), "end": None})
                first_interest[actor] = first_interest[actor] or at
        if milestone is None and valid and all(active.values()):
            milestone = at
    if cutoff >= terminal_at:
        for actor in participants:
            if intervals[actor] and intervals[actor][-1]["end"] is None:
                intervals[actor][-1]["end"] = _iso(terminal_at)
            active[actor] = False
    lag = timedelta(seconds=followup["ingestion_lag_seconds"])
    mature = cutoff >= deadline + lag
    complete = (observed["complete_through"] is not None
                and observed["complete_through"] >= min(cutoff, deadline) and not orphan_actions)
    post_deadline = milestone + timedelta(seconds=followup["post_milestone_seconds"]) if milestone else None
    completion_deadline = deadline + timedelta(seconds=followup["completion_seconds"])
    post_mature = post_deadline is not None and cutoff >= post_deadline + lag
    post_complete = (post_deadline is not None and observed["post_milestone_complete_through"] is not None
                     and observed["post_milestone_complete_through"] >= min(cutoff, post_deadline)
                     and not any(_time(e["at"], "at") <= post_deadline for e in stale_after_completion))
    post_reversals = [r for r in reversals if _time(r["at"], "at") <= post_deadline] if milestone else []
    post_validity = [r for r in validity_attrition if _time(r["at"], "at") <= post_deadline] if milestone else []
    completed_at = min(completions) if completions else None
    supported_completion = observation["completion_supported"]
    completion_complete = (supported_completion and observed["completion_complete_through"] is not None
                           and observed["completion_complete_through"] >= min(cutoff, completion_deadline))
    counterparty = None
    if any(t is not None for t in first_interest.values()):
        first_actor = min((p for p in participants if first_interest[p] is not None), key=lambda p: (first_interest[p], p))
        other_actor = next(p for p in participants if p != first_actor)
        other_view = exposure[other_actor]
        if other_view is not None and other_view < deadline:
            counterparty = {
                "first_actor_id": first_actor,
                "exposure_lag_seconds": (other_view - first_interest[first_actor]).total_seconds(),
                "first_interest_active_at_exposure": any(
                    _time(span["start"], "start") <= other_view
                    and (span["end"] is None or other_view < _time(span["end"], "end"))
                    for span in intervals[first_actor]),
            }
    confirmed_absent = bool(post_mature and terminal_reason in {"expire", "expired"}
                            and terminal_at <= post_deadline and not any(t <= post_deadline for t in completions))
    ledger = [{key: event.get(key) for key in (
        "event_id", "at", "type", "actor_id", "sequence", "target_event_id", "verified",
        "provider_transaction_id", "exposure_qualified", "evidence_class")}
        for event in ordered if _time(event["at"], "at") <= cutoff
        and event["type"] not in {"delivered", "redisplay"}]
    ledger_hash = hashlib.sha256(json.dumps(ledger, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "version": VERSION, "episode_id": episode_id, "concept_id": concept,
        "participants": participants, "origin": origin, "cutoff": _iso(cutoff),
        "generated_at": _iso(generated), "start_at": _iso(start), "deadline": _iso(deadline),
        "selected_source_credit": selected or ("shared" if len(sources) > 1 else "unknown"),
        "exposure_sources": sorted(exposure_sources), "event_count": len(unique),
        "event_ledger_hash": ledger_hash,
        "historical_mutual": milestone is not None, "mutual_at": _iso(milestone),
        "later_attrition": reversals,
        "validity_attrition": validity_attrition,
        "stale_after_completion_actions": stale_after_completion,
        "currently_actionable_mutual": all(active.values()) and cutoff < terminal_at,
        "lifecycle": {"state": "closed" if cutoff >= terminal_at else "open",
                      "reason": terminal_reason if cutoff >= terminal_at else None, "closed_at": _iso(terminal_at) if cutoff >= terminal_at else None},
        "maturity": {"elapsed": mature, "mature_at": _iso(deadline + lag)},
        "observation": {"complete": complete, "orphan_actions": orphan_actions},
        "actors": {p: {"exposed_at": _iso(exposure[p]), "interest_intervals": intervals[p],
                        "expressed_interest": first_interest[p] is not None,
                        "first_interest_at": _iso(first_interest[p]), "decision": decisions[p],
                        "had_explicit_decision": any(e["actor_id"] == p for e in seen_decisions.values()),
                        "active_interest": active[p]} for p in participants},
        "counterparty_after_first_interest": counterparty,
        "post_milestone": {"deadline": _iso(post_deadline), "elapsed": post_mature,
                           "complete": post_complete, "reversals": post_reversals,
                           "validity_attrition": post_validity,
                           "non_reversed": not post_reversals if post_mature and post_complete else None,
                           "both_confirmed": all(any(milestone <= t <= post_deadline for t in times) for times in confirmations.values()) if milestone else False,
                           "remaining_validity_seconds": max(0, (deadline - milestone).total_seconds()) if milestone else None,
                           "time_at_risk_seconds": max(0, (min(cutoff, terminal_at, post_deadline) - milestone).total_seconds()) if milestone else None,
                           "expired_without_confirmed_outcome": confirmed_absent,
                           "expired_without_completion": confirmed_absent if completion_complete else None},
        "completion": {"supported": supported_completion, "elapsed": cutoff >= completion_deadline + lag,
                       "complete": completion_complete, "deadline": _iso(completion_deadline),
                       "verified_at": _iso(completed_at), "verified_by_horizon": any(t <= completion_deadline for t in completions),
                       "provider_send_count": len(send_times)},
        "willingness_probability": None,
    }


def summarize_cohort(cohort, episodes, cutoff):
    """Fixed pre-assignment manager-league yields; no inferred preference labels.

All eligible members, including no-request, empty, and failed searches, remain.
Unmeasured yield is a lower bound with an unknown (unbounded) upper bound;
counts per member are not binomial probabilities. Statistical uncertainty is
left explicitly unestimated until a cluster analysis plan is preregistered.
"""
    cutoff = _time(cutoff, "cutoff")
    cohort_id = _id(cohort.get("cohort_id"), "cohort_id")
    _id(cohort.get("eligibility_rule"), "eligibility_rule")
    frozen = _time(cohort.get("frozen_at"), "frozen_at")
    start = _time(cohort.get("window_start"), "window_start")
    end = _time(cohort.get("window_end"), "window_end")
    if not frozen <= start < end:
        raise ValueError("cohort: require frozen_at <= window_start < window_end")
    followup = _followup(cohort.get("followup"))
    members = cohort.get("members")
    if not isinstance(members, list):
        raise ValueError("members: explicit fixed eligible list required")
    by_member = {}
    cluster_arms = {}
    for member in members:
        for key in ("manager_id", "league_id", "cluster_id", "assignment_arm"):
            _id(member.get(key), f"member.{key}")
        assigned = _time(member.get("assigned_at"), "assigned_at")
        if not frozen <= assigned <= start:
            raise ValueError("eligibility must be frozen before assignment and origin window")
        key = (member["manager_id"], member["league_id"])
        if key in by_member:
            raise ValueError("duplicate eligible manager-league")
        count = member.get("request_count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("request_count: nonnegative integer required, including empty/error requests")
        if not isinstance(member.get("observation_complete"), bool):
            raise ValueError("member observation_complete: boolean required")
        cluster = member["cluster_id"]
        if cluster in cluster_arms and cluster_arms[cluster] != member["assignment_arm"]:
            raise ValueError("assignment must be constant within connected cluster")
        cluster_arms[cluster] = member["assignment_arm"]
        by_member[key] = member
    reduced, quarantined, seen_episodes = [], [], {}
    for episode in episodes:
        if not isinstance(episode, dict):
            quarantined.append({"episode_id": None, "reason": "episode: mapping required"})
            continue
        episode_id = episode.get("episode_id")
        serialized = json.dumps(episode, sort_keys=True, default=str)
        if isinstance(episode_id, str) and episode_id in seen_episodes:
            if seen_episodes[episode_id] != serialized:
                raise ValueError(f"conflicting duplicate episode {episode_id}")
            continue
        if isinstance(episode_id, str):
            seen_episodes[episode_id] = serialized
        try:
            result = reduce_episode(episode, cutoff)
            if _followup(episode.get("followup")) != followup:
                raise ValueError("episode followup differs from frozen cohort")
            reduced.append(result)
        except ValueError as exc:
            quarantined.append({"episode_id": episode_id, "reason": str(exc)})
    included, excluded = [], []
    for result in reduced:
        origin = result["origin"]
        member = by_member.get((origin["manager_id"], origin["league_id"]))
        if origin["cohort_id"] != cohort_id or member is None:
            reason = "outside_cohort"
        elif origin["assignment_arm"] != member["assignment_arm"]:
            reason = "assignment_conflict"
        elif _time(result["start_at"], "start_at") < _time(member["assigned_at"], "assigned_at"):
            reason = "carry_in"
        elif _time(result["generated_at"], "generated_at") < _time(member["assigned_at"], "assigned_at"):
            reason = "pre_generated_inventory"
        elif not start <= _time(result["start_at"], "start_at") < end:
            reason = "outside_origin_window"
        else:
            reason = None
        if reason:
            excluded.append({"episode_id": result["episode_id"], "reason": reason})
        else:
            included.append(result)
    concepts = {}
    for result in included:
        concepts.setdefault(result["concept_id"], []).append(result)
    credits, completion_credits, ambiguous, ambiguous_history = [], [], [], []
    for concept, rows in sorted(concepts.items()):
        # An origin is immutable; contradictory origins are not resolved by
        # choosing whichever later surface, arm, or manager looks favorable.
        origin_keys = {tuple(r["origin"][key] for key in (
            "cohort_id", "manager_id", "league_id", "request_id", "assignment_arm",
            "model_id", "model_version", "selected_source")) for r in rows}
        if len(origin_keys) != 1:
            ambiguous.append(concept)
            continue
        overlapping_conflict = any(
            _time(left["start_at"], "start_at") < _time(right["deadline"], "deadline")
            and _time(right["start_at"], "start_at") < _time(left["deadline"], "deadline")
            and (left["event_ledger_hash"] != right["event_ledger_hash"]
                 or left["start_at"] != right["start_at"] or left["deadline"] != right["deadline"])
            for i, left in enumerate(rows) for right in rows[i + 1:])
        if overlapping_conflict:
            # Do not silently select a short/missing history because it has an
            # earlier episode identifier. A verified historical overlap remains
            # an observed lower bound, but retention/labels cannot be trusted
            # until the caller reconciles these competing representations.
            ambiguous_history.append(concept)
            quarantined.append({"concept_id": concept, "episode_ids": sorted(r["episode_id"] for r in rows),
                                "scope": "outcome_history", "reason": "overlapping_episode_histories_require_reconciliation"})
            for row in rows:
                row["observation"].update(complete=False, history_ambiguous=True)
                row["post_milestone"].update(complete=False, non_reversed=None)
        mutual = [r for r in rows if r["historical_mutual"]]
        if mutual:
            credits.append(min(mutual, key=lambda r: (_time(r["mutual_at"], "mutual_at"), r["episode_id"])))
        completed = [r for r in rows if r["completion"]["verified_by_horizon"]]
        if completed:
            completion_credits.append(min(completed, key=lambda r: (_time(r["completion"]["verified_at"], "verified_at"), r["episode_id"])))
    n = len(members)
    mature_at = end + timedelta(seconds=EPISODE_SECONDS + followup["ingestion_lag_seconds"])
    mature = cutoff >= mature_at
    complete_members = sum(m["observation_complete"] for m in members)
    complete = (complete_members == n and not quarantined and not ambiguous
                and not any(row["reason"] == "assignment_conflict" for row in excluded)
                and all(r["observation"]["complete"] for r in included))
    post_rows = [r for r in credits if r["post_milestone"]["elapsed"] and r["post_milestone"]["complete"]]
    retained = sum(r["post_milestone"]["non_reversed"] is True for r in post_rows)
    mature_episodes = [r for r in included if r["maturity"]["elapsed"]]
    observed_episodes = [r for r in mature_episodes if r["observation"]["complete"]]
    actors = [a for r in observed_episodes for a in r["actors"].values() if a["exposed_at"] is not None and _time(a["exposed_at"], "exposed_at") < _time(r["deadline"], "deadline")]
    responders = [a for a in actors if a["decision"] in _DECISION]
    dual = [r for r in observed_episodes if all(a["exposed_at"] is not None and _time(a["exposed_at"], "exposed_at") < _time(r["deadline"], "deadline") for a in r["actors"].values())]
    counterparties = [r for r in observed_episodes if r["counterparty_after_first_interest"] is not None]
    by_arm = {}
    for arm in sorted({m["assignment_arm"] for m in members}):
        denominator = sum(m["assignment_arm"] == arm for m in members)
        arm_rows = [r for r in credits if r["origin"]["assignment_arm"] == arm]
        by_arm[arm] = {"primary_yield": _ratio(len(arm_rows), denominator),
                       "non_reversed_yield": _ratio(sum(r["post_milestone"]["non_reversed"] is True for r in arm_rows), denominator)}
    leagues = sorted({m["league_id"] for m in members})
    league_yields = [_ratio(sum(r["origin"]["league_id"] == league for r in credits), sum(m["league_id"] == league for m in members))["value"] for league in leagues]
    reversals = sum(r["post_milestone"]["non_reversed"] is False for r in post_rows)
    confirmations = sum(r["post_milestone"]["both_confirmed"] for r in post_rows)
    guardrails = cohort.get("guardrails")
    guardrail_status, failures = "unratified", []
    if guardrails is not None:
        if not isinstance(guardrails, dict):
            raise ValueError("guardrails: explicit declaration mapping required")
        _id(guardrails.get("preregistration_id"), "guardrails.preregistration_id")
        for key in ("max_reversal_rate", "min_confirmation_rate", "min_followup_coverage"):
            limit = guardrails.get(key)
            if limit is not None and (isinstance(limit, bool) or not isinstance(limit, (int, float)) or not math.isfinite(limit) or not 0 <= limit <= 1):
                raise ValueError(f"guardrails.{key}: expected fraction in [0,1]")
        coverage = len(post_rows) / len(credits) if credits else None
        declared = (guardrails.get("min_followup_coverage") is not None
                    and any(guardrails.get(key) is not None for key in ("max_reversal_rate", "min_confirmation_rate")))
        guardrail_status = "evidence-limited" if declared else "unratified"
        if declared and mature and complete and post_rows and coverage >= guardrails["min_followup_coverage"]:
            checks = {"max_reversal_rate": reversals / len(post_rows), "min_confirmation_rate": confirmations / len(post_rows)}
            for key, value in checks.items():
                limit = guardrails.get(key)
                if limit is not None and ((key.startswith("max") and value > limit) or (key.startswith("min") and value < limit)):
                    failures.append(key)
            guardrail_status = "failed" if failures else "within_declared_limits"
    return {
        "version": VERSION, "cohort_id": cohort_id, "cutoff": _iso(cutoff),
        "primary_yield": _ratio(len(credits), n), "primary_interpretation": "observed distinct mutual concepts per fixed eligible manager-league; not a probability",
        "maturity": {"elapsed": mature, "mature_at": _iso(mature_at)},
        "coverage": _ratio(complete_members, n), "observation_complete": complete,
        "yield_bounds": {"lower": len(credits) / n if n else None, "upper": len(credits) / n if n and complete and mature else None},
        "league_macro_yield": sum(league_yields) / len(league_yields) if league_yields else None,
        "cluster_count": len(cluster_arms), "uncertainty": {"interval": None, "reason": "cluster-aware inference requires a preregistered analysis; no independent-card confidence interval"},
        "by_assignment_arm": by_arm,
        "request_yield": _ratio(len(credits), sum(m["request_count"] for m in members)),
        "request_frequency": _ratio(sum(m["request_count"] for m in members), n),
        "no_request_rate": _ratio(sum(m["request_count"] == 0 for m in members), n),
        "episode_conversion": _ratio(sum(r["historical_mutual"] for r in mature_episodes), len(mature_episodes)),
        "responder_conditional_like_share": _ratio(sum(a["decision"] in _POSITIVE for a in responders), len(responders)),
        "response_coverage": _ratio(len(responders), len(actors)),
        "exposed_interest_conversion": _ratio(sum(a["expressed_interest"] for a in actors), len(actors)),
        "dual_exposed_mutual_conversion": _ratio(sum(r["historical_mutual"] for r in dual), len(dual)),
        "counterparty_conversion_after_first_interest": _ratio(sum(r["historical_mutual"] for r in counterparties), len(counterparties)),
        "counterparty_by_active_interest_at_exposure": {
            str(active).lower(): _ratio(
                sum(r["historical_mutual"] for r in counterparties if r["counterparty_after_first_interest"]["first_interest_active_at_exposure"] == active),
                sum(r["counterparty_after_first_interest"]["first_interest_active_at_exposure"] == active for r in counterparties))
            for active in (False, True)},
        "no_remaining_decision_count": sum(a["decision"] is None for a in actors),
        "nonresponse_count": sum(not a["had_explicit_decision"] for a in actors),
        "withdrawn_or_undone_decision_count": sum(a["had_explicit_decision"] and a["decision"] is None for a in actors),
        "non_reversed_yield": _ratio(retained, n), "post_milestone_coverage": _ratio(len(post_rows), len(credits)),
        "post_milestone_reversal_rate": _ratio(reversals, len(post_rows)),
        "post_milestone_confirmation_rate": _ratio(confirmations, len(post_rows)),
        "post_milestone_attrition_by_reason": {
            reason: _ratio(sum(any(e["type"] == reason for e in r["post_milestone"]["reversals"]) for r in post_rows), len(post_rows))
            for reason in ("withdraw", "undo", "pass", "reject", "cancel")},
        "post_milestone_validity_attrition_by_reason": {
            reason: _ratio(sum(any(e["type"] == reason for e in r["post_milestone"]["validity_attrition"]) for r in post_rows), len(post_rows))
            for reason in ("invalidate", "expire")},
        "expired_without_confirmed_outcome_rate": _ratio(sum(r["post_milestone"]["expired_without_confirmed_outcome"] for r in post_rows), len(post_rows)),
        "verified_completion_yield": _ratio(len(completion_credits), n),
        "completion_support": _ratio(sum(r["completion"]["supported"] for r in included), len(included)),
        "completion_observation_coverage": _ratio(sum(r["completion"]["complete"] and r["completion"]["elapsed"] for r in included), len(included)),
        "post_completion_stale_action_episodes": sum(bool(r["stale_after_completion_actions"]) for r in included),
        "guardrails": {"status": guardrail_status, "failures": failures, "declaration": deepcopy(guardrails)},
        "promotion": "not_evaluated", "willingness_probability": None,
        "quarantined": quarantined, "excluded_episodes": excluded,
        "ambiguous_origin_concepts": ambiguous, "episodes": reduced,
        "ambiguous_history_concepts": ambiguous_history,
        "observed_product_mutual_concepts": sum(any(r["historical_mutual"] for r in rows) for rows in concepts.values()),
    }
