"""Prepared inventory's private JSON/card/evidence boundary (Lane C).

This module never writes a database, publishes a card, or records activity.
The caller authenticates the scope and checks current dependencies before
restore, then commits each returned evidence batch before exposing its cards.
JSON checks establish integrity/binding, not independent model correctness.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import fields
from datetime import datetime, timezone

from .deck_diagnostics import compact_rows, dumps as diagnostic_dumps, REFERENCE_KEY
from .trade_gen_owner import OwnerDecisionContext
from .trade_service import TradeCard

VERSION = "prepared-trade-payload-1"
CARD_VERSION = "prepared-runtime-card-1"
# Deliberate schema, not dataclass introspection: future fields need review.
CARD_FIELDS = frozenset("""trade_id league_id proposing_user_id target_user_id
target_username give_player_ids receive_player_ids mismatch_score fairness_score
composite_score created_at expires_at decision reasons match_context narrative
basis likes_you sweetener gap_sweetener partner_fit need_fit consensus_fit
block_boosted outlook_dir lane lane_shift fit_premium aggression_variant
give_value receive_value relaxed relaxed_reason rationale meso_variants health
tier standing_offer_reason source_like_impression_id standing_offer_mine""".split())
DYNAMIC_FIELDS = frozenset("""preserve_server_order owner_group owner_groups
owner_surface_group fatigue_retest wildcard wildcard_pool_size wildcard_provenance
fit fit_diag breaker breaker_shadow roster_evaluation negmem_stamp""".split())
# These have already been projected by the authoritative logger into the
# evidence bundle. Copying full request boards per runtime card is both unsafe
# for memory and unnecessary for decisions/pending-card consumers.
CAPTURE_ONLY_FIELDS = frozenset(("owner_request_evidence", "owner_generation_diagnostics",
                                 "owner_route_experiment"))
PUBLIC_FIELDS = frozenset("""trade_id league_id target_user_id target_username give
receive mismatch_score fairness_score composite_score basis decision expires_at
preserve_server_order model_arm generator_version selection_coverage selection_notice
give_value receive_value favors gap likes_you standing_offer_reason standing_offer_mine
sweetener gap_sweetener retest wildcard relaxed relaxed_reason roster_evaluation
partner_fit need_fit fit breaker lane fit_premium aggression_variant reasons rationale
meso_variants tier narrative match_context real_opponent outlook impression_id""".split())
PLAYER_FIELDS = frozenset("""id name position team age years_experience depth_chart_position
depth_chart_order injury_status injury_body_part birth_date height weight college
search_rank adp pick_value on_block""".split())
ROW_FIELDS = frozenset("""impression_id user_id league_id deck_job_id card_index
trade_hash features_json propensity base_score final_score archetype shape_bucket
served_at centerpiece_id is_ghost policy_version candidate_set_id candidate_set_size
assets_json model_arm arm_rank fairness_threshold group_key group_rank lane_slot
trade_intent valuation_json trade_concept_id policy_variant source_like_impression_id""".split())
PROOF_FIELDS = frozenset(f.name for f in fields(OwnerDecisionContext))
_PROOF_VERSIONS = {("owner_v1", "owner-v1"),
                   ("owner_v2_bilateral", "owner-v2-bilateral-1"),
                   ("owner_v2_bilateral", "owner-v2-bilateral-2")}


def _require(condition, reason):
    if not condition:
        raise ValueError("prepared_payload:" + reason)


def _copy(value, *, tuples=False):
    """Detach only JSON types; no default=str, objects, nonfinite or key coercion."""
    remaining = [1_000_000]
    def visit(item, depth=0):
        remaining[0] -= 1
        _require(depth <= 80 and remaining[0] >= 0, "json_complexity")
        if item is None or type(item) in (str, bool, int):
            return item
        if type(item) is float:
            _require(math.isfinite(item), "nonfinite")
            return item
        if type(item) is dict:
            _require(all(type(k) is str for k in item), "json_key")
            return {k: visit(v, depth + 1) for k, v in item.items()}
        if type(item) is list or (tuples and type(item) is tuple):
            return [visit(v, depth + 1) for v in item]
        raise ValueError("prepared_payload:unsupported_json_type")
    return visit(value)


def _json(raw):
    _require(type(raw) is str, "json_text_required")
    def pairs(values):
        result = {}
        for key, value in values:
            _require(key not in result, "duplicate_json_key")
            result[key] = value
        return result
    try:
        return _copy(json.loads(raw, object_pairs_hook=pairs,
                                parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite"))))
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError("prepared_payload:invalid_json") from exc


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _keys(value, allowed, required=None):
    _require(type(value) is dict and set(value) <= allowed
             and (required or set()) <= set(value), "fields")


def _text(value, *, empty=False):
    _require(type(value) is str and (empty or bool(value)), "text")
    return value


def _ids(value, *, empty=False):
    _require(type(value) is list and (empty or bool(value)), "asset_ids")
    for item in value:
        _text(item)
    _require(len(set(value)) == len(value), "duplicate_assets")
    return value


def _number(value):
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    _require(valid, "number")


def _date(value):
    if isinstance(value, datetime):
        parsed = value
    else:
        _text(value)
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("prepared_payload:timestamp") from exc
    _require(parsed.tzinfo is not None and parsed.utcoffset() is not None, "timestamp_timezone")
    return parsed.astimezone(timezone.utc)


def _trade_hash(give, receive, target):
    # Existing F1 identity, pinned against the server helper in integration tests.
    return hashlib.sha256(f"{','.join(sorted(give))}|{','.join(sorted(receive))}|{target}".encode()).hexdigest()[:16]


def _proof(record, card):
    _keys(record, PROOF_FIELDS, PROOF_FIELDS)
    _require(record["eligible"] is True and record["reason"] == "eligible", "ineligible_proof")
    data = _json(record["snapshot_json"])
    _require(type(data) is dict and type(data.get("schema_version")) is int
             and data["schema_version"] == 1, "proof_schema")
    _text(data.get("generator"))
    _text(data.get("generator_version"))
    _require((data["generator"], data["generator_version"]) in _PROOF_VERSIONS
             and data.get("eligible") is True and data.get("reason") == "eligible", "proof_schema")
    for side in ("give_ids", "receive_ids"):
        _ids(record[side])
    for key in ("league_id", "user_id", "target_user_id"):
        _text(record[key])
    market = data.get("market")
    _require(type(market) is dict, "proof_market")
    for key in ("give", "receive", "ratio", "effective_floor"):
        _number(market.get(key))
    proof = OwnerDecisionContext(**{**record, "give_ids": tuple(record["give_ids"]),
                                    "receive_ids": tuple(record["receive_ids"])})
    _require(proof.matches(card), "proof_binding")
    assets = data.get("assets")
    _require(type(assets) is list and all(type(a) is dict for a in assets)
             and [a.get("id") for a in assets] == card.give_player_ids + card.receive_player_ids,
             "proof_assets")
    return proof


def _public(public, card, proof):
    _keys(public, PUBLIC_FIELDS, {"trade_id", "league_id", "target_user_id", "give", "receive", "expires_at"})
    for key in ("trade_id", "league_id", "target_user_id", "expires_at"):
        _require(public[key] == getattr(card, key), "public_identity")
    for side, ids in (("give", card.give_player_ids), ("receive", card.receive_player_ids)):
        _require(type(public[side]) is list, "public_assets")
        for player in public[side]:
            _keys(player, PLAYER_FIELDS, {"id"})
        _require([p["id"] for p in public[side]] == ids, "public_assets")
    for key in ("mismatch_score", "fairness_score", "composite_score", "give_value", "receive_value",
                "decision", "target_username", "basis", "lane", "aggression_variant"):
        if key in public:
            _require(_canonical(public[key]) == _canonical(getattr(card, key)), "public_value")
    if proof is not None:
        data = proof.as_dict()
        _require(public.get("model_arm") == data["generator"]
                 and public.get("generator_version") == data["generator_version"], "public_model")
    else:
        _require(not ({"model_arm", "generator_version"} & set(public)), "unbound_public_model")
    # Public projection is not permitted to smuggle private counterparty boards.
    if isinstance(public.get("rationale"), dict):
        other = public["rationale"].get("counterparty")
        _require(not isinstance(other, dict) or "own_board_gain" not in other, "public_private_value")
    _require(all(type(v) is dict and "recipient_value_delta_pct" not in v
                 for v in public.get("meso_variants", [])), "public_private_value")


def capture_runtime_card(card, public_card, *, significance=None):
    """Capture an exact TradeCard, never a service, arbitrary class or attrs.

    significance is a trusted server-side (context, selected_give, selected_receive)
    record, NOT anything copied from public JSON. New object-key registration is
    the publisher's responsibility, after commitment.
    """
    _require(type(card) is TradeCard, "card_type")
    _require(set(vars(card)) <= CARD_FIELDS | DYNAMIC_FIELDS | CAPTURE_ONLY_FIELDS
             | {"owner_evaluation", "owner_published"}, "unsupported_runtime_field")
    _require(not getattr(card, "owner_published", False), "already_published")
    runtime = {key: getattr(card, key) for key in CARD_FIELDS}
    dynamic = {key: getattr(card, key) for key in DYNAMIC_FIELDS if hasattr(card, key)}
    proof = getattr(card, "owner_evaluation", None)
    _require(proof is None or type(proof) is OwnerDecisionContext, "proof_type")
    record = _copy({"schema": CARD_VERSION, "runtime": runtime, "dynamic": dynamic,
                    "owner_evaluation": ({key: getattr(proof, key) for key in PROOF_FIELDS}
                                         if proof is not None else None),
                    "significance": significance, "public": public_card}, tuples=True)
    restore_runtime_card(record, user_id=card.proposing_user_id, league_id=card.league_id)
    return record


def restore_runtime_card(record, *, user_id, league_id):
    """Validate and hydrate only allowlisted fields, without pricing/evaluation."""
    record = _copy(record)
    keys = {"schema", "runtime", "dynamic", "owner_evaluation", "significance", "public"}
    _keys(record, keys, keys)
    _require(record["schema"] == CARD_VERSION, "card_schema")
    runtime, dynamic = record["runtime"], record["dynamic"]
    _keys(runtime, CARD_FIELDS, CARD_FIELDS)
    _keys(dynamic, DYNAMIC_FIELDS)
    for key in ("trade_id", "league_id", "proposing_user_id", "target_user_id"):
        _text(runtime[key])
    _text(runtime["target_username"], empty=True)
    _require(runtime["proposing_user_id"] == user_id and runtime["league_id"] == league_id,
             "card_scope")
    _require(runtime["target_user_id"] != user_id, "self_trade")
    give, receive = _ids(runtime["give_player_ids"]), _ids(runtime["receive_player_ids"])
    _require(not set(give) & set(receive), "overlapping_assets")
    _require(runtime["decision"] is None, "prepared_decision")
    _require(_date(runtime["created_at"]) < _date(runtime["expires_at"]), "card_expiry")
    for key in ("mismatch_score", "fairness_score", "composite_score"):
        _number(runtime[key])
    for key in ("partner_fit", "need_fit", "consensus_fit", "outlook_dir", "lane_shift",
                "give_value", "receive_value"):
        if runtime[key] is not None:
            _number(runtime[key])
    for key in ("likes_you", "block_boosted", "relaxed"):
        _require(type(runtime[key]) is bool, "runtime_boolean")
    _text(runtime["basis"])
    for key in ("narrative", "lane", "aggression_variant", "relaxed_reason", "tier", "standing_offer_reason"):
        if runtime[key] is not None:
            _text(runtime[key], empty=True)
    for key in ("match_context", "sweetener", "gap_sweetener", "fit_premium", "rationale",
                "health", "standing_offer_mine"):
        _require(runtime[key] is None or type(runtime[key]) is dict, "runtime_mapping")
    _require(type(runtime["reasons"]) is list and all(type(v) is str for v in runtime["reasons"]),
             "runtime_reasons")
    _require(runtime["meso_variants"] is None or (type(runtime["meso_variants"]) is list
             and all(type(v) is dict for v in runtime["meso_variants"])), "runtime_variants")
    for key in ("preserve_server_order", "fatigue_retest", "wildcard"):
        _require(key not in dynamic or type(dynamic[key]) is bool, "runtime_boolean")
    for key in ("owner_group", "owner_surface_group"):
        if key in dynamic:
            _text(dynamic[key])
    for key in ("wildcard_provenance", "fit", "fit_diag", "breaker", "breaker_shadow",
                "roster_evaluation", "negmem_stamp"):
        _require(key not in dynamic or dynamic[key] is None or type(dynamic[key]) is dict, "runtime_mapping")
    if "wildcard_pool_size" in dynamic:
        _require(type(dynamic["wildcard_pool_size"]) is int and dynamic["wildcard_pool_size"] >= 0,
                 "runtime_count")
    source = runtime["source_like_impression_id"]
    if source is not None:
        _text(source)
        _require(runtime["likes_you"], "source_without_interest")
    significance = record["significance"]
    if significance is not None:
        _require(type(significance) is list and len(significance) == 3
                 and significance[0] in ("inbound", "explicit_search"), "significance")
        _ids(significance[1], empty=True)
        _ids(significance[2], empty=True)
        if significance[0] == "inbound":
            _require(runtime["likes_you"] and not significance[1] and not significance[2], "inbound_provenance")
        else:
            _require(bool(set(significance[1]) & set(give) or set(significance[2]) & set(receive)),
                     "selection_provenance")
    if "owner_groups" in dynamic:
        _ids(dynamic["owner_groups"], empty=True)
        dynamic["owner_groups"] = tuple(dynamic["owner_groups"])
    card = TradeCard(**runtime)
    for name, value in dynamic.items():
        setattr(card, name, value)
    evidence = record["owner_evaluation"]
    proof = _proof(evidence, card) if evidence is not None else None
    if proof is not None:
        card.owner_evaluation = proof
    _public(record["public"], card, proof)
    return card


def _scope(row, user_id, league_id, job_id):
    _require(row.get("user_id") == user_id and row.get("league_id") == league_id
             and row.get("deck_job_id") == job_id, "evidence_scope")


def _snapshots(rows, user_id, job_id):
    """Verify scoped, content-addressed DAG before any publication callback."""
    nodes = {}
    for row in rows:
        required = {"snapshot_id", "user_id", "deck_job_id", "created_at", "payload_json"}
        _keys(row, required, required)
        _require(row["user_id"] == user_id and row["deck_job_id"] == job_id, "snapshot_scope")
        _date(row["created_at"])
        sid = _text(row["snapshot_id"])
        _require(sid not in nodes, "duplicate_snapshot")
        nodes[sid] = _json(row["payload_json"])
    expanded, visiting = {}, set()
    def expand(value, depth=0):
        _require(depth <= 80, "snapshot_depth")
        if type(value) is dict:
            if REFERENCE_KEY in value:
                _require(set(value) == {REFERENCE_KEY} and type(value[REFERENCE_KEY]) is str,
                         "snapshot_reference")
                return node(value[REFERENCE_KEY], depth + 1)
            return {k: expand(v, depth + 1) for k, v in value.items()}
        if type(value) is list:
            return [expand(v, depth + 1) for v in value]
        return value
    def node(sid, depth):
        _require(sid in nodes and sid not in visiting, "snapshot_missing_or_cycle")
        if sid not in expanded:
            visiting.add(sid)
            result = _copy(expand(nodes[sid], depth))
            digest = hashlib.sha256((diagnostic_dumps((user_id, job_id)) + "\n"
                                     + diagnostic_dumps(result)).encode()).hexdigest()
            _require(digest == sid, "snapshot_checksum")
            expanded[sid] = result
            visiting.remove(sid)
        return expanded[sid]
    for sid in nodes:
        node(sid, 0)
    return expand


class PreparedEvidenceCapture:
    """The logger's two *preparation-only* write callbacks; no DB imports.

    Wire candidate_set(row) instead of save_deck_candidate_set and
    impressions(rows) instead of save_deck_impressions. Never run the normal
    on_batch_committed callback for these writes. finish seals the full result.
    """
    def __init__(self, *, user_id, league_id, job_id):
        self.user_id, self.league_id, self.job_id = map(_text, (user_id, league_id, job_id))
        self._candidate = None
        self._rows, self._nodes = [], {}
        self._finished = False

    def candidate_set(self, row):
        _require(not self._finished and self._candidate is None, "capture_state")
        row = _copy(row)
        _scope(row, self.user_id, self.league_id, self.job_id)
        self._candidate = row

    def impressions(self, rows):
        _require(not self._finished and type(rows) is list, "capture_state")
        detached = _copy(rows, tuples=True)
        for row in detached:
            _scope(row, self.user_id, self.league_id, self.job_id)
            if type(row.get("features_json")) is str:
                row["features_json"] = _json(row["features_json"])
        compacted, nodes = compact_rows(detached)
        for node in nodes:
            old = self._nodes.get(node["snapshot_id"])
            _require(old is None or old == node, "snapshot_conflict")
            self._nodes[node["snapshot_id"]] = node
        self._rows.extend(compacted)

    def finish(self, cards, public_cards, *, significance_by_trade_id=None):
        _require(not self._finished and len(cards) == len(public_cards), "capture_state")
        significance = significance_by_trade_id or {}
        _require(set(significance) <= {c.trade_id for c in cards}, "orphan_significance")
        bundle = {"schema": VERSION, "user_id": self.user_id, "league_id": self.league_id,
                  "job_id": self.job_id, "cards": [capture_runtime_card(c, p,
                      significance=significance.get(c.trade_id)) for c, p in zip(cards, public_cards)],
                  "candidate_set": self._candidate, "impressions": self._rows,
                  "snapshots": list(self._nodes.values())}
        restore_inventory(bundle, user_id=self.user_id, league_id=self.league_id, now=None)
        self._finished = True
        return _copy(bundle)


def _candidate(row, *, user_id, league_id, job_id):
    if row is None:
        return None
    keys = {"candidate_set_id", "deck_job_id", "user_id", "league_id", "size", "set_hash",
            "candidates_json", "created_at"}
    _keys(row, keys, keys)
    _scope(row, user_id, league_id, job_id)
    _text(row["candidate_set_id"])
    _date(row["created_at"])
    members = _json(row["candidates_json"])
    _require(type(members) is list and type(row["size"]) is int and row["size"] == len(members), "candidate_count")
    for member in members:
        keys = {"trade_hash", "partner", "give", "receive", "base_score", "in_deck"}
        _keys(member, keys, keys)
        _ids(member["give"])
        _ids(member["receive"])
        _text(member["partner"])
        _number(member["base_score"])
        _require(type(member["in_deck"]) is bool, "candidate_membership")
        _require(member["trade_hash"] == _trade_hash(member["give"], member["receive"], member["partner"]),
                 "candidate_terms")
    digest = hashlib.sha256("|".join(sorted(m["trade_hash"] for m in members)).encode()).hexdigest()[:16]
    _require(row["set_hash"] == digest, "candidate_checksum")
    return members


class PreparedInventory:
    """Validated, request-local data. Not a freshness receipt or published job."""
    def __init__(self, bundle, cards, rows, ghosts):
        self._bundle, self._rows, self._ghosts = bundle, rows, ghosts
        self.cards = cards
        self.public_cards = [_copy(r["public"]) for r in bundle["cards"]]
        self.significance_by_trade_id = {c.trade_id: (r["significance"][0],
            tuple(r["significance"][1]), tuple(r["significance"][2]))
            for c, r in zip(cards, bundle["cards"]) if r["significance"] is not None}
        self.candidate_set = _copy(bundle["candidate_set"])

    def _unchanged(self, index):
        """Disposition may remove an occurrence, never change its frozen terms."""
        baseline = self._bundle["cards"][index]
        captured = capture_runtime_card(self.cards[index], self.public_cards[index],
                                       significance=baseline["significance"])
        _require(_canonical(captured) == _canonical(baseline), "restored_card_mutated")
        expected = baseline["significance"]
        actual = self.significance_by_trade_id.get(self.cards[index].trade_id)
        _require(_copy(actual, tuples=True) == expected, "restored_provenance_mutated")

    def batches(self, *, served_at, trade_ids=None, first_batch_size=30, batch_size=100,
                first_deck=False, board_state=None):
        """Yield detached evidence/public slices. Caller commits, THEN publishes.

        Exact surviving subsequences are allowed, never reranking. Original
        prepared positions remain in captured presentation diagnostics; actual
        served positions are written to card_index. No views/actions are minted.
        """
        stamp = _date(served_at)
        _require(type(served_at) is str, "served_at_text")
        _require(type(first_deck) is bool, "first_deck")
        for size in (first_batch_size, batch_size):
            _require(type(size) is int and size > 0, "batch_size")
        ids = [c.trade_id for c in self.cards]
        wanted = ids if trade_ids is None else _ids(trade_ids, empty=True)
        wanted_set = set(wanted)
        _require([i for i in ids if i in wanted_set] == wanted, "adoption_order")
        if board_state is not None:
            _require(type(board_state) in (list, tuple) and len(board_state) == 2
                     and type(board_state[0]) is int and board_state[0] >= 0, "board_state")
            if board_state[1] is not None:
                _date(board_state[1])
        selected = [(i, c) for i, c in enumerate(self.cards) if c.trade_id in wanted_set]
        # Validate the entire selection before producing even its first batch.
        _require(all(stamp < _date(c.expires_at) for _, c in selected), "expired_card")
        _require(_canonical(self.candidate_set) == _canonical(self._bundle["candidate_set"]),
                 "restored_candidate_mutated")
        for index, _ in selected:
            self._unchanged(index)
        cursor, limit, served_position, first_batch = 0, first_batch_size, 0, True
        while cursor < len(selected) or (cursor == 0 and self._ghosts):
            selection = selected[cursor:cursor + limit]
            rows, public, cards = [], [], []
            for index, card in selection:
                self._unchanged(index)
                row = _copy(self._rows[index])
                row["served_at"], row["card_index"] = served_at, served_position
                served_position += 1
                features = _json(row["features_json"])
                features.pop("first_deck", None)
                if first_deck:
                    features["first_deck"] = True
                if board_state is not None:
                    features.update(ranked_player_count=board_state[0], last_board_update_at=board_state[1],
                                    user_value_basis="personal" if board_state[0] else "consensus")
                row["features_json"] = features
                rows.append(row)
                public.append({**_copy(self.public_cards[index]), "impression_id": row["impression_id"]})
                cards.append(card)
            cursor += len(selection)
            if cursor >= len(selected):
                for ghost in self._ghosts:
                    row = _copy(ghost)
                    row["served_at"] = served_at
                    rows.append(row)
            yield {"cards": cards, "public_cards": public, "impression_rows": rows,
                   "candidate_set": _copy(self.candidate_set) if first_batch else None}
            first_batch = False
            if cursor >= len(selected):
                break
            limit = batch_size


def restore_inventory(bundle, *, user_id, league_id, now):
    """Validate complete structure/dependencies before returning any usable card.

    now=None is only for sealing a new capture. Adoption must supply an aware
    UTC clock. This does not replace current-input/account/source validation.
    """
    bundle = _copy(bundle)
    keys = {"schema", "user_id", "league_id", "job_id", "cards", "candidate_set", "impressions", "snapshots"}
    _keys(bundle, keys, keys)
    _require(bundle["schema"] == VERSION, "schema")
    _require(bundle["user_id"] == user_id and bundle["league_id"] == league_id, "scope")
    job_id = _text(bundle["job_id"])
    _require(all(type(bundle[k]) is list for k in ("cards", "impressions", "snapshots")), "inventory_lists")
    cards = [restore_runtime_card(r, user_id=user_id, league_id=league_id) for r in bundle["cards"]]
    _require(len({c.trade_id for c in cards}) == len(cards), "duplicate_trade_id")
    if now is not None:
        _require(all(_date(now) < _date(c.expires_at) for c in cards), "expired_card")
    expand = _snapshots(bundle["snapshots"], user_id, job_id)
    candidate = bundle["candidate_set"]
    members = _candidate(candidate, user_id=user_id, league_id=league_id, job_id=job_id)
    in_deck = {m["trade_hash"] for m in (members or []) if m["in_deck"]}
    exact_in_deck = {(tuple(m["give"]), tuple(m["receive"]), m["partner"])
                     for m in (members or []) if m["in_deck"]}
    rows, ghosts, impression_ids = [], [], set()
    required = {"impression_id", "user_id", "league_id", "deck_job_id", "card_index",
                "trade_hash", "features_json", "propensity", "served_at"}
    for raw in bundle["impressions"]:
        _keys(raw, ROW_FIELDS, required)
        _scope(raw, user_id, league_id, job_id)
        iid = _text(raw["impression_id"])
        _require(iid not in impression_ids, "duplicate_impression")
        impression_ids.add(iid)
        _date(raw["served_at"])
        _number(raw["propensity"])
        _require(raw["propensity"] >= 0, "propensity")
        for key in ("base_score", "final_score", "fairness_threshold"):
            if raw.get(key) is not None:
                _number(raw[key])
        for key in ("arm_rank", "group_rank", "candidate_set_size"):
            if raw.get(key) is not None:
                _require(type(raw[key]) is int and raw[key] >= 0, "evidence_count")
        _require(type(raw["card_index"]) is int and raw["card_index"] >= 0, "card_index")
        _require(raw.get("is_ghost") in (None, 0, 1) and type(raw.get("is_ghost")) is not bool, "ghost")
        features = _copy(expand(_json(raw["features_json"])))
        _require(type(features) is dict, "features")
        row = {**raw, "features_json": json.dumps(features, allow_nan=False)}
        if row.get("source_like_impression_id") is not None:
            _text(row["source_like_impression_id"])
        if row.get("valuation_json") is not None:
            _require(type(_json(row["valuation_json"])) is dict, "valuation")
        assets = None
        if row.get("assets_json") is not None:
            assets = _json(row["assets_json"])
            _keys(assets, {"give", "receive"}, {"give", "receive"})
            _ids(assets["give"])
            _ids(assets["receive"])
            _require(not set(assets["give"]) & set(assets["receive"]), "evidence_assets")
            _text(features.get("partner_user_id"))
            _require(row["trade_hash"] == _trade_hash(assets["give"], assets["receive"],
                                                     features["partner_user_id"]), "evidence_terms")
        if candidate is not None:
            _require(row.get("candidate_set_id") == candidate["candidate_set_id"]
                     and row.get("candidate_set_size") == candidate["size"]
                     and row["trade_hash"] in in_deck, "candidate_link")
            _require(assets is not None and (tuple(assets["give"]), tuple(assets["receive"]),
                     features.get("partner_user_id")) in exact_in_deck, "candidate_terms")
        else:
            _require(row.get("candidate_set_id") is None and row.get("candidate_set_size") is None,
                     "missing_candidate_set")
        if row.get("is_ghost") == 1:
            ghosts.append(row)
            continue
        index = len(rows)
        _require(index < len(cards) and row["card_index"] == index, "evidence_order")
        card, public = cards[index], bundle["cards"][index]["public"]
        _require(row["trade_hash"] == _trade_hash(card.give_player_ids, card.receive_player_ids,
                                                 card.target_user_id), "evidence_terms")
        _require(features.get("partner_user_id") == card.target_user_id, "evidence_partner")
        _require(row.get("source_like_impression_id") == card.source_like_impression_id, "source_link")
        _require(public.get("impression_id", iid) == iid, "public_impression")
        if assets is not None:
            _require(assets == {"give": card.give_player_ids, "receive": card.receive_player_ids},
                     "evidence_assets")
        proof = getattr(card, "owner_evaluation", None)
        if proof is not None:
            _require(_canonical(_json(row.get("valuation_json"))) == _canonical(proof.as_dict()), "evidence_proof")
            _require(row.get("model_arm") == proof.as_dict()["generator"], "evidence_model")
        rows.append(row)
    _require(len(rows) == len(cards), "incomplete_evidence")
    return PreparedInventory(bundle, cards, rows, ghosts)
