"""Read-only legacy evidence adapter for the bilateral scorecard.

Only explicit local SQLite snapshots or exported JSON rows are accepted. This
module never imports the application/database, reads environment credentials,
or opens a writable database. Aggregate output is the default; private records
require ``include_records=True``. No legacy event is promoted to a verified
episode, fixed experimental cohort, acceptance probability, or completion.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3


VERSION = "scorecard-evidence-v1"
REFERENCE_KEY = "$deck_diagnostic_v1"

# This is both the SQL allowlist and the export boundary. In particular, there
# are no credential, current-board, free-text pass-reason, or provider-raw fields.
TABLE_COLUMNS = {
    "deck_impressions": "impression_id user_id league_id deck_job_id card_index trade_hash features_json propensity base_score final_score archetype shape_bucket served_at centerpiece_id is_ghost policy_version candidate_set_id candidate_set_size assets_json model_arm arm_rank fairness_threshold group_key group_rank lane_slot trade_intent valuation_json trade_concept_id policy_variant source_like_impression_id".split(),
    "deck_outcomes": "id impression_id action dwell_ms detail_expanded calc_opened acted_at".split(),
    "trade_decisions": "id user_id league_id trade_id give_player_ids receive_player_ids decision created_at retracted_at impression_id trade_concept_id".split(),
    "trade_pass_reasons": "impression_id user_id league_id trade_id key_source reason detail switched_from elo_signal_at created_at updated_at".split(),
    "trade_matches": "id league_id user_a_id user_b_id user_a_give user_a_receive matched_at status user_a_decision user_b_decision user_a_decided_at user_b_decided_at user_a_dismissed user_b_dismissed trade_concept_id user_a_impression_id user_b_impression_id first_like_at second_like_at match_latency_seconds match_valuation_json".split(),
    "trade_proposals": "id proposal_event_id impression_id match_id user_id league_id target_user_id provider provider_transaction_id source give_asset_ids receive_asset_ids origin_trade_hash final_trade_hash edited_from_source valuation_json proposed_at".split(),
    "bakeoff_runs": "run_id deck_job_id user_id league_id arm_order served_arm deck_size total_ms arms_json agreement_json groups_json config_json created_at".split(),
    "deck_diagnostic_snapshots": "snapshot_id user_id deck_job_id created_at payload_json".split(),
    "deck_candidate_sets": "candidate_set_id deck_job_id user_id league_id size set_hash candidates_json created_at".split(),
    "suggestion_trade_links": "id transaction_id league_id was_recommended matched_impression_id match_type overlap_score ghost_impression_id ghost_match_type ghost_overlap_score traded_at computed_at".split(),
    "sleeper_trades": "id transaction_id league_id week traded_at synced_at roster_ids adds drops draft_picks waiver_budget".split(),
}
PRIMARY_KEYS = {name: columns[0] for name, columns in TABLE_COLUMNS.items()}
EVIDENCE_FIELDS = ("model_arm", "policy_version", "concept_id", "partner_identity", "served_at",
                   "verified_view_event", "frozen_owner_context", "owner_request", "market_asof",
                   "actual_expiry", "fixed_preassignment_cohort", "projection_backed_lineup",
                   "independent_fairness_annotation")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _reject_constant(value):
    raise ValueError("nonfinite JSON number")


def _json(value, expected):
    if value is None or value == "":
        return None, "missing"
    try:
        parsed = json.loads(value, parse_constant=_reject_constant) if isinstance(value, str) else deepcopy(value)
        _canonical(parsed)
    except (TypeError, ValueError, RecursionError):
        return None, "malformed"
    if not isinstance(parsed, expected):
        return None, "wrong_type"
    return parsed, "present"


def _local_file(path):
    value = str(path)
    if "://" in value or value.startswith("file:") or value == ":memory:":
        raise ValueError("an explicit local snapshot file is required")
    result = Path(path).expanduser().resolve(strict=True)
    if not result.is_file():
        raise ValueError("snapshot must be a regular file")
    return result


def load_sqlite_snapshot(path):
    """Return allowlisted rows from an explicit, already-created local snapshot.

    ``mode=ro`` is enforced in the URI. Query-only mode provides a second write
    barrier; a transaction gives the multi-table read one consistent snapshot.
    Views and virtual tables are refused, and names never come from caller SQL.
    Use an operator-created backup, not a changing application's database.
    """
    snapshot = _local_file(path)
    rows = {}
    conn = sqlite3.connect(snapshot.as_uri() + "?mode=ro", uri=True)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only = ON")
        conn.execute("PRAGMA trusted_schema = OFF")
        conn.execute("BEGIN")
        schemas = {r["name"]: r for r in conn.execute(
            "SELECT name, type, sql FROM sqlite_master WHERE type IN ('table', 'view')")}
        for table, allowed in TABLE_COLUMNS.items():
            if table not in schemas:
                continue
            schema = schemas[table]
            if schema["type"] != "table" or "VIRTUAL TABLE" in (schema["sql"] or "").upper():
                raise ValueError("evidence sources must be ordinary tables")
            available = {r["name"] for r in conn.execute(f'PRAGMA table_info("{table}")')}
            selected = [column for column in allowed if column in available]
            if not selected:
                rows[table] = []
                continue
            columns = ", ".join(f'"{column}"' for column in selected)
            rows[table] = [dict(r) for r in conn.execute(f'SELECT {columns} FROM "{table}"')]
    finally:
        conn.close()
    return rows


def load_export(path):
    """Load ``{tables: {table_name: [rows]}}`` or the bare table mapping.

    Unknown tables/columns are excluded, including free text. A malformed
    outer export fails explicitly; malformed JSON *inside* a row is audited.
    """
    with _local_file(path).open(encoding="utf-8") as stream:
        data = json.load(stream, parse_constant=_reject_constant)
    if isinstance(data, dict) and "tables" in data:
        data = data["tables"]
    return _select_rows(data)


def _select_rows(tables):
    if not isinstance(tables, dict):
        raise ValueError("evidence export must be a table mapping")
    result = {}
    for table, allowed in TABLE_COLUMNS.items():
        if table not in tables:
            continue
        if not isinstance(tables[table], list) or any(not isinstance(row, dict) for row in tables[table]):
            raise ValueError(f"{table} must contain a list of rows")
        result[table] = [{key: deepcopy(row[key]) for key in allowed if key in row}
                         for row in tables[table]]
    return result


def _ref(table, row):
    return {"table": table, "key": PRIMARY_KEYS[table], "value": row.get(PRIMARY_KEYS[table])}


def _timestamp(value):
    if not isinstance(value, str) or not value:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _capture_timestamp(value):
    """Occurrence capture needs a timezone; never guess one for legacy rows."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value if parsed.tzinfo is not None else None
    except ValueError:
        return None


def _asset_bundle(value):
    assets, state = _json(value, dict)
    if state != "present":
        return assets, state
    if any(not isinstance(assets.get(side), list) or not assets[side]
           or any(not isinstance(pid, str) or not pid for pid in assets[side])
           for side in ("give", "receive")):
        return assets, "invalid_assets"
    all_ids = assets["give"] + assets["receive"]
    if len(set(all_ids)) != len(all_ids):
        return assets, "duplicate_or_overlapping_assets"
    return assets, "present"


def _resolve(value, scope, snapshots, issues, visiting=frozenset()):
    if isinstance(value, dict) and set(value) == {REFERENCE_KEY}:
        sid = value[REFERENCE_KEY]
        if not isinstance(sid, str):
            issues.add("malformed_diagnostic_reference")
            return {"diagnostic_status": "malformed_reference"}
        if sid in visiting:
            issues.add("cyclic_diagnostic_reference")
            return {"diagnostic_status": "cyclic_reference", "snapshot_id": sid}
        matches = snapshots.get((*scope, sid), [])
        if len(matches) != 1:
            issues.add("expired_missing_or_ambiguous_diagnostic")
            return {"diagnostic_status": "expired_missing_or_ambiguous", "snapshot_id": sid}
        payload, state = _json(matches[0].get("payload_json"), (dict, list))
        if state != "present":
            issues.add("malformed_diagnostic_payload")
            return {"diagnostic_status": state, "snapshot_id": sid}
        return _resolve(payload, scope, snapshots, issues, visiting | {sid})
    if isinstance(value, dict):
        return {k: _resolve(v, scope, snapshots, issues, visiting) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve(v, scope, snapshots, issues, visiting) for v in value]
    return value


def _snapshot_binding(snapshot, assets, assets_state):
    if snapshot is None or assets_state != "present":
        return "unknown"
    entries = snapshot.get("assets")
    if isinstance(entries, dict):
        if any(not isinstance(entries.get(side), list) or any(not isinstance(a, dict) for a in entries[side])
               for side in ("give", "receive")):
            return "mismatch"
        return "exact_directional" if all(
            [a.get("id") for a in entries[side]] == assets[side] for side in ("give", "receive")) else "mismatch"
    if isinstance(entries, list) and all(isinstance(a, dict) for a in entries):
        # Owner schema stores a flat give+receive array. The writer verifies
        # orientation before persistence; retain that weaker schema fact.
        return "owner_flat_give_then_receive" if [a.get("id") for a in entries] == assets["give"] + assets["receive"] else "mismatch"
    return "unknown"


def audit_rows(tables, *, include_records=False):
    """Produce a detached reproducible coverage manifest, optionally private data.

    Coverage is evidence presence, never metric validity. No chronology is
    inferred from match A/B names, no duplicate gestures reduced, and no current
    table or live input can repair a historical snapshot. The neutral records
    deliberately require the versioned scorecard evaluator to make judgments.
    """
    tables = _select_rows(tables)
    ordered = {table: sorted(rows, key=_canonical) for table, rows in sorted(tables.items())}
    manifest = {
        "schema_version": VERSION,
        "source_rows_sha256": hashlib.sha256(_canonical(ordered).encode()).hexdigest(),
        "tables": {table: {"available": table in tables, "rows": len(tables.get(table, [])),
                   "columns_present": sorted({k for row in tables.get(table, []) for k in row})}
                   for table in TABLE_COLUMNS},
        "fixed_eligible_cohort": {"status": "absent", "reason": "legacy logs do not establish frozen preassignment eligibility"},
        "claim_limits": ["coverage is not quality", "persisted impressions are not verified views",
                         "provider sends are not confirmed completions", "legacy ordering propensity is not an assignment probability",
                         "missing or purged evidence is not reconstructed", "no verified episode or causal comparison is inferred"],
    }
    snapshots = {}
    for row in tables.get("deck_diagnostic_snapshots", []):
        snapshots.setdefault((row.get("user_id"), row.get("deck_job_id"), row.get("snapshot_id")), []).append(row)
    impressions = tables.get("deck_impressions", [])
    by_id = {}
    for row in impressions:
        by_id.setdefault(row.get("impression_id"), []).append(row)
    counts, issues_count, coverage = Counter(), Counter(), Counter({key: 0 for key in EVIDENCE_FIELDS})
    events = []
    events_by_impression = {}
    for row in tables.get("deck_outcomes", []):
        linked = by_id.get(row.get("impression_id"), [])
        state = "linked" if len(linked) == 1 and row.get("impression_id") else "orphan_or_ambiguous"
        actor = linked[0].get("user_id") if state == "linked" else None
        action = row.get("action")
        action_known = action in {"viewed", "like", "pass", "undo", "propose", "not_interested"}
        counts["outcome_" + (action if action_known else "unknown_action")] += 1
        counts["outcome_" + state] += 1
        event = {"source": _ref("deck_outcomes", row), "impression_id": row.get("impression_id"),
                 "actor_id": actor, "action": action, "acted_at": row.get("acted_at"),
                 "link_status": state, "raw": row}
        events.append(event)
        if state == "linked":
            events_by_impression.setdefault(row["impression_id"], []).append(event)
    records = []
    for row in impressions:
        issues = set()
        assets, asset_state = _asset_bundle(row.get("assets_json"))
        features, feature_state = _json(row.get("features_json"), dict)
        valuation, valuation_state = _json(row.get("valuation_json"), dict)
        for name, state in (("assets", asset_state), ("features", feature_state), ("valuation", valuation_state)):
            coverage[name + ":" + state] += 1
        features = _resolve(features or {}, (row.get("user_id"), row.get("deck_job_id")), snapshots, issues)
        binding = _snapshot_binding(valuation, assets, asset_state)
        coverage["snapshot_binding:" + binding] += 1
        if binding == "mismatch":
            issues.add("valuation_asset_mismatch")
        if not row.get("impression_id") or len(by_id.get(row.get("impression_id"), [])) != 1:
            issues.add("missing_or_duplicate_impression_id")
        linked_events = events_by_impression.get(row.get("impression_id"), [])
        views = [event for event in linked_events if event["action"] == "viewed" and _timestamp(event["acted_at"])]
        if any(not _timestamp(event["acted_at"]) for event in linked_events):
            issues.add("invalid_event_timestamp")
        ghost = row.get("is_ghost") == 1
        if ghost and views:
            issues.add("ghost_with_view_event")
        viewed = bool(views) and not ghost
        counts["persisted_occurrences"] += 1
        counts["ghost_occurrences"] += int(ghost)
        counts["view_event_occurrences"] += int(viewed)
        owner = valuation if isinstance((valuation or {}).get("assets"), list) else {}
        source = "likes_you" if row.get("source_like_impression_id") or features.get("likes_you") else "recorded_constructor" if row.get("model_arm") else "unknown"
        evidence_presence = {
            "model_arm": bool(row.get("model_arm")), "policy_version": bool(row.get("policy_version")),
            "concept_id": bool(row.get("trade_concept_id")), "partner_identity": bool(features.get("partner_user_id")),
            "served_at": bool(row.get("served_at")), "verified_view_event": viewed,
            "frozen_owner_context": bool(owner), "owner_request": isinstance(features.get("owner_request", {}).get("input"), dict) if isinstance(features.get("owner_request"), dict) else False,
            "market_asof": _timestamp((valuation or {}).get("market", {}).get("consensus_asof")) if isinstance((valuation or {}).get("market"), dict) else False,
            "actual_expiry": False, "fixed_preassignment_cohort": False,
            "projection_backed_lineup": False, "independent_fairness_annotation": False,
        }
        coverage.update(name for name, present in evidence_presence.items() if present)
        issues_count.update(issues)
        records.append({"source": _ref("deck_impressions", row), "occurrence_id": row.get("impression_id"),
            "actor_id": row.get("user_id"), "partner_id": features.get("partner_user_id"),
            "league_id": row.get("league_id"), "job_id": row.get("deck_job_id"),
            "concept_id": row.get("trade_concept_id"), "assets": assets,
            "assets_status": asset_state, "snapshot_binding": binding,
            "served_at": row.get("served_at"), "expires_at": None,
            "view_events": [event["source"] for event in views], "has_view_event": viewed,
            "stage": "withheld_ghost" if ghost else "persisted_occurrence",
            "model_arm": row.get("model_arm"), "model_version": (valuation or {}).get("generator_version"),
            "policy_version": row.get("policy_version"), "delivery_source": source,
            "also_proposed_by": features.get("also_proposed_by"),
            "source_like_impression_id": row.get("source_like_impression_id"),
            "valuation": valuation, "features": features, "evidence_presence": evidence_presence,
            "issues": sorted(issues), "raw": row})
    counts["confirmed_provider_sends"] = len(tables.get("trade_proposals", []))
    counts["stored_matches_not_yet_episode_verified"] = len(tables.get("trade_matches", []))
    counts["captured_completed_provider_transactions_unlinked_to_episodes"] = len(tables.get("sleeper_trades", []))
    counts["verified_exact_episode_completions"] = 0
    counts["pass_reason_rows_not_additional_actions"] = len(tables.get("trade_pass_reasons", []))
    manifest.update(counts=dict(sorted(counts.items())), occurrence_coverage=dict(sorted(coverage.items())),
                    integrity_issues=dict(sorted(issues_count.items())))
    if include_records:
        manifest["private_records"] = {"occurrences": records, "events": events,
                                       "source_tables": tables}
    return manifest


def frozen_owner_requests(tables):
    """Extract full captured owner requests for authorized local replay only.

    These are request-input units, not fixed experiment enrollment. Invalid or
    non-owner run config remains represented with a status and source key.
    """
    records = []
    for row in _select_rows(tables).get("bakeoff_runs", []):
        config, status = _json(row.get("config_json"), dict)
        if status == "present" and not isinstance(config.get("input"), dict):
            status = "no_frozen_owner_input"
        records.append({"source": _ref("bakeoff_runs", row), "status": status,
                        "assignment": config, "created_at": row.get("created_at"),
                        "fixed_preassignment_cohort": False})
    return records


def occurrence_to_offer(occurrence):
    """Map captured facts to the dimensional evaluator without inventing inputs.

    Owner/policy scores never become review labels. Missing ownership, kind,
    source vintage, tiers, projections or independent reviews stay missing and
    the dimension evaluator reports the affected integrity/coverage limits.
    Market ``as_of`` is source vintage, not the serve-time capture timestamp.
    """
    if occurrence.get("assets_status") != "present":
        raise ValueError("valid captured exact assets are required")
    if occurrence.get("snapshot_binding") not in {"exact_directional", "owner_flat_give_then_receive"}:
        raise ValueError("asset-bound frozen valuation is required")
    valuation = occurrence.get("valuation") or {}
    features = occurrence.get("features") or {}
    request = features.get("owner_request") or features.get("owner_experiment") or {}
    inputs = request.get("input", {}) if isinstance(request, dict) else {}
    inputs = inputs if isinstance(inputs, dict) else {}
    players = inputs.get("players") or {}
    players = players if isinstance(players, dict) else {}
    snapshot_id = hashlib.sha256(_canonical({"valuation": valuation, "features": features,
        "source": occurrence.get("source")}).encode()).hexdigest()
    owner_schema = isinstance(valuation.get("assets"), list)
    asset_rows = valuation["assets"] if owner_schema else sum(
        [valuation["assets"].get(side, []) for side in ("give", "receive")], [])
    asset_map = {row["id"]: row for row in asset_rows}
    offer = {"schema_version": 1, "offer_id": occurrence.get("occurrence_id"),
             "snapshot_id": snapshot_id, "data_kind": "captured_legacy_evidence",
             "captured_at": _capture_timestamp(occurrence.get("served_at")),
             "assets": {}, "managers": {}, "evidence": {},
             "source": deepcopy(occurrence.get("source")),
             "adapter_limits": ["no independent review labels", "source vintages may be absent",
                                "personal tier/order universe not reconstructed from model scores",
                                "dynasty roster proxies are not projections"]}
    for role, side, manager_id, side_key in (
            ("A", "give", occurrence.get("actor_id"), "viewer"),
            ("B", "receive", occurrence.get("partner_id"), "counterparty")):
        context = valuation.get(side_key) or {}
        context = context if isinstance(context, dict) else {}
        roster = context.get("roster_ids")
        roster = roster if isinstance(roster, list) else None
        manager = {"manager_id": manager_id, "give": deepcopy(occurrence["assets"][side])}
        if roster is not None:
            manager["roster"] = deepcopy(roster)
        if context.get("outlook_source") in {"declared", "inferred"}:
            manager["selected_outlook" if context["outlook_source"] == "declared" else "inferred_outlook"] = context.get("outlook")
        offer["managers"][role] = manager
        positions = features.get("give_positions" if side == "give" else "receive_positions")
        for index, pid in enumerate(manager["give"]):
            data = players.get(pid) or {}
            data = data if isinstance(data, dict) else {}
            position = data.get("position")
            if isinstance(positions, list) and len(positions) == len(manager["give"]) and positions[index] == "PICK":
                position = "PICK"
            asset = {"market_value": asset_map[pid].get("market" if owner_schema else "market_value")}
            if roster is not None and pid in roster:
                asset["owner_id"] = manager_id
            if position == "PICK":
                asset["kind"] = "pick"
            elif position in {"QB", "RB", "WR", "TE", "K", "DEF", "DL", "LB", "DB"}:
                asset.update(kind="player", position=position)
            if "age" in data:
                asset["age"] = data["age"]
            offer["assets"][pid] = asset
    market = valuation.get("market") or {}
    market = market if isinstance(market, dict) else {}
    vintage = market.get("consensus_asof") or (request.get("market_as_of") if isinstance(request, dict) else None)
    offer["evidence"]["market"] = {"units": "captured_dynasty_value", "universe_id": "package:" + snapshot_id,
        "provenance": {"source": "frozen_occurrence_valuation", "as_of": vintage if _timestamp(vintage) else None,
                       "version": valuation.get("schema_version"), "snapshot_id": snapshot_id}}
    return offer
