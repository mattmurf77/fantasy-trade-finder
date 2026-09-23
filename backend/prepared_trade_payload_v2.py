"""Bounded prepared-inventory codec; storage readers are injected, never imported.

Native construction is unchanged. This boundary holds a page, a bounded raw
diagnostic cache and compact identity indexes, never an expanded inventory.
The existing strict native-card/proof parser remains the authority for cards.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import json
import math
from itertools import zip_longest

from . import prepared_trade_payload as v1
from .deck_diagnostics import compact_rows, REFERENCE_KEY

VERSION = "prepared-trade-payload-2"
VALIDATOR_VERSION = "prepared-semantic-validator-1"
MAX_RECORD_BYTES = 4 * 1024 * 1024
MAX_CANDIDATE_BYTES = 2 * 1024 * 1024 - 4096
PAGE_TARGET_BYTES = 1024 * 1024
MAX_PAGE_RECORDS = 100
MAX_PARSED_NODES = 200_000
MAX_EXPANDED_BYTES = 8 * 1024 * 1024
MAX_EXPANDED_NODES = 200_000
MAX_BATCH_BYTES = 8 * 1024 * 1024
RAW_CACHE_BYTES = 2 * 1024 * 1024
MAX_RAW_CLOSURE_BYTES = 8 * 1024 * 1024
MAX_DEPTH = 80
ADMISSION_FIELDS = frozenset("""ordinal trade_id give_player_ids receive_player_ids
target_user_id likes_you standing_offer_reason source_like_impression_id impression_id
expires_at""".split())


class PreparedPayloadError(ValueError):
    """A fixed codec invariant failed, distinct from current inputs or I/O."""


def is_artifact_error(error):
    """Recognize only typed v2 guards and the unchanged v1 codec namespace.

    Generic ValueError, callback/history failures and database exceptions do
    not justify retiring a valid stored inventory. The store has its own typed
    InvalidArtifact marker; callers combine it with this narrow codec check.
    """
    return (isinstance(error, PreparedPayloadError)
            or type(error) is ValueError and str(error).startswith("prepared_payload:"))


def _require(condition, reason):
    if not condition:
        raise PreparedPayloadError("prepared_payload_v2:" + reason)


def _primitive(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":")).encode("ascii")


def _size(value, limit=MAX_RECORD_BYTES, node_limit=MAX_PARSED_NODES):
    """Check plain input before copying/encoding it; account repeated aliases."""
    nodes, size = 0, 0
    def add(count):
        nonlocal size
        size += count
        _require(size <= limit, "record_bytes")
    def visit(item, depth):
        nonlocal nodes
        nodes += 1
        _require(nodes <= node_limit and depth <= MAX_DEPTH, "record_complexity")
        if type(item) is dict:
            _require(all(type(k) is str for k in item), "json_key")
            add(2 + max(0, len(item) - 1))
            for key, child in item.items():
                _require(len(key) <= limit, "record_bytes")
                add(len(_primitive(key)) + 1)
                visit(child, depth + 1)
        elif type(item) in (list, tuple):
            add(2 + max(0, len(item) - 1))
            for child in item:
                visit(child, depth + 1)
        else:
            _require(item is None or type(item) in (str, bool, int, float), "json_type")
            if type(item) is str:
                _require(len(item) <= limit, "record_bytes")
            if type(item) is float:
                _require(math.isfinite(item), "nonfinite")
            add(len(_primitive(item)))
    visit(value, 0)
    return size


def _json(raw, limit=MAX_RECORD_BYTES):
    """Bound bytes and lexical structure BEFORE allocating a decoded graph."""
    _require(type(raw) is str and len(raw) <= limit and len(raw.encode()) <= limit, "json_bytes")
    depth = tokens = 0
    quoted = escaped = atom = False
    for char in raw:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted, atom = True, False
            tokens += 1
        elif char in "[{":
            depth += 1
            tokens += 1
            atom = False
        elif char in "]}":
            depth -= 1
            atom = False
        elif char.isspace() or char in ",:":
            atom = False
        elif not atom:
            tokens += 1
            atom = True
        _require(0 <= depth <= MAX_DEPTH and tokens <= MAX_PARSED_NODES, "json_complexity")
    def pairs(values):
        result = {}
        for key, value in values:
            _require(key not in result, "duplicate_json_key")
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
    except (ValueError, TypeError, RecursionError) as exc:
        raise PreparedPayloadError("prepared_payload_v2:invalid_json") from exc
    _size(value, limit)
    return value


def _detach(value, limit=MAX_RECORD_BYTES):
    _size(value, limit)
    return v1._copy(value, tuples=True)


class DiagnosticResolver:
    """Scoped original DAG; expansion budgets precede any expanded allocation."""
    def __init__(self, reader, *, user_id, job_id):
        self.reader, self.user_id, self.job_id = reader, user_id, job_id
        self._raw = OrderedDict()
        self._raw_bytes = 0
        self._stats = OrderedDict()
        self._active_raw_bytes = 0

    def _load(self, sid):
        v1._text(sid)
        if sid in self._raw:
            self._raw.move_to_end(sid)
            _require(self._active_raw_bytes + self._raw[sid][2] <= MAX_RAW_CLOSURE_BYTES,
                     "snapshot_closure_bytes")
            return self._raw[sid][:2]
        rows = self.reader.get_nodes([sid])
        _require(type(rows) is dict and sid in rows, "missing_snapshot")
        row = rows[sid]
        v1._keys(row, {"snapshot_id", "user_id", "deck_job_id", "created_at", "payload_json"},
                 {"snapshot_id", "user_id", "deck_job_id", "created_at", "payload_json"})
        _require(row["snapshot_id"] == sid and row["user_id"] == self.user_id
                 and row["deck_job_id"] == self.job_id, "snapshot_scope")
        v1._date(row["created_at"])
        _require(type(row["payload_json"]) is str and len(row["payload_json"]) <= MAX_RECORD_BYTES,
                 "json_bytes")
        size = len(row["payload_json"].encode())
        _require(self._active_raw_bytes + size <= MAX_RAW_CLOSURE_BYTES, "snapshot_closure_bytes")
        value = _json(row["payload_json"])
        if size <= RAW_CACHE_BYTES:
            while self._raw and self._raw_bytes + size > RAW_CACHE_BYTES:
                _, old = self._raw.popitem(last=False)
                self._raw_bytes -= old[2]
            self._raw[sid] = row, value, size
            self._raw_bytes += size
        return row, value

    @staticmethod
    def _ref(value):
        if type(value) is dict and REFERENCE_KEY in value:
            _require(set(value) == {REFERENCE_KEY} and type(value[REFERENCE_KEY]) is str,
                     "snapshot_reference")
            return value[REFERENCE_KEY]
        return None

    def _measure(self, value, visiting, depth=0):
        _require(depth <= MAX_DEPTH, "snapshot_depth")
        sid = self._ref(value)
        if sid is not None:
            size, nodes, height = self._measure_node(sid, visiting, depth + 1)
            return size, nodes, height + 1
        if type(value) in (dict, list):
            children = value.values() if type(value) is dict else value
            size, nodes, height = 2 + max(0, len(value) - 1), 1, 0
            if type(value) is dict:
                size += sum(len(_primitive(key)) + 1 for key in value)
            for child in children:
                child_size, child_nodes, child_height = self._measure(child, visiting, depth + 1)
                size, nodes = size + child_size, nodes + child_nodes
                height = max(height, child_height + 1)
                _require(size <= MAX_EXPANDED_BYTES and nodes <= MAX_EXPANDED_NODES,
                         "snapshot_amplification")
            _require(depth + height <= MAX_DEPTH, "snapshot_depth")
            return size, nodes, height
        return len(_primitive(value)), 1, 0

    def _measure_node(self, sid, visiting, depth=0):
        _require(sid not in visiting and depth <= MAX_DEPTH, "snapshot_cycle_or_depth")
        if sid in self._stats:
            self._stats.move_to_end(sid)
            _require(depth + self._stats[sid][2] <= MAX_DEPTH, "snapshot_depth")
            return self._stats[sid]
        row, value = self._load(sid)
        raw_bytes = len(row["payload_json"].encode())
        self._active_raw_bytes += raw_bytes
        try:
            size, nodes, height = self._measure(value, visiting | {sid}, depth + 1)
        finally:
            self._active_raw_bytes -= raw_bytes
        stats = size, nodes, height + 1
        _require(depth + stats[2] <= MAX_DEPTH, "snapshot_depth")
        _require(stats[0] <= MAX_EXPANDED_BYTES and stats[1] <= MAX_EXPANDED_NODES,
                 "snapshot_amplification")
        digest = hashlib.sha256(_primitive((self.user_id, self.job_id)) + b"\n")
        for chunk in self._emit(value):
            digest.update(chunk)
        _require(digest.hexdigest() == sid, "snapshot_checksum")
        self._stats[sid] = stats
        while len(self._stats) > 128:
            self._stats.popitem(last=False)
        return stats

    def _emit(self, value, depth=0):
        _require(depth <= MAX_DEPTH, "snapshot_depth")
        sid = self._ref(value)
        if sid is not None:
            yield from self._emit(self._load(sid)[1], depth + 1)
        elif type(value) is dict:
            yield b"{"
            for index, key in enumerate(sorted(value)):
                if index:
                    yield b","
                yield _primitive(key)
                yield b":"
                yield from self._emit(value[key], depth + 1)
            yield b"}"
        elif type(value) is list:
            yield b"["
            for index, child in enumerate(value):
                if index:
                    yield b","
                yield from self._emit(child, depth + 1)
            yield b"]"
        else:
            yield _primitive(value)

    def validate_node(self, sid):
        return self._measure_node(sid, frozenset())

    def _materialize(self, value, depth=0):
        _require(depth <= MAX_DEPTH, "snapshot_depth")
        sid = self._ref(value)
        if sid is not None:
            return self._materialize(self._load(sid)[1], depth + 1)
        if type(value) is dict:
            return {key: self._materialize(child, depth + 1) for key, child in value.items()}
        if type(value) is list:
            return [self._materialize(child, depth + 1) for child in value]
        return value

    def expand(self, value):
        stats = self._measure(value, frozenset())
        _require(stats[0] <= MAX_EXPANDED_BYTES and stats[1] <= MAX_EXPANDED_NODES,
                 "snapshot_amplification")
        return self._materialize(value)

    def closure(self, values):
        found, total = {}, 0
        def visit(value):
            nonlocal total
            sid = self._ref(value)
            if sid is not None:
                self.validate_node(sid)
                if sid not in found:
                    row, body = self._load(sid)
                    total += _size(row)
                    _require(total <= MAX_BATCH_BYTES, "closure_bytes")
                    found[sid] = row
                    visit(body)
            elif type(value) is dict:
                for child in value.values():
                    visit(child)
            elif type(value) is list:
                for child in value:
                    visit(child)
        for value in values:
            visit(value)
        return list(found.values())


class _Overlay:
    def __init__(self, reader, nodes):
        self.reader, self.nodes = reader, nodes

    def get_nodes(self, ids):
        result = self.reader.get_nodes([sid for sid in ids if sid not in self.nodes])
        result.update({sid: self.nodes[sid] for sid in ids if sid in self.nodes})
        return result


class _PageWriter:
    def __init__(self, stage, kind):
        self.stage, self.kind = stage, kind
        self.page_index = self.ordinal = self.size = 0
        self.records = []

    def append(self, record):
        size = _size(record)
        if self.records and (self.size + size + 2 > PAGE_TARGET_BYTES or len(self.records) >= MAX_PAGE_RECORDS):
            self.flush()
        self.records.append(_detach(record))
        self.size += size + 1

    def flush(self):
        if self.records:
            self.stage.append_page(kind=self.kind, page_index=self.page_index,
                                   ordinal_start=self.ordinal, records=self.records)
            self.ordinal += len(self.records)
            self.page_index += 1
            self.records, self.size = [], 0


class PagedPreparedEvidenceCapture:
    paged = True

    def __init__(self, *, stage, user_id, league_id, job_id):
        self.stage = stage
        self.user_id, self.league_id, self.job_id = map(v1._text, (user_id, league_id, job_id))
        self._candidate = None
        self._candidate_seen = self._finished = False
        self._rows = _PageWriter(stage, "impressions")
        self._count = self._ghosts = 0

    def candidate_set(self, row):
        _require(not self._finished and not self._candidate_seen, "capture_state")
        _size(row, MAX_CANDIDATE_BYTES)
        _json(row["candidates_json"], MAX_CANDIDATE_BYTES)
        v1._candidate(row, user_id=self.user_id, league_id=self.league_id, job_id=self.job_id)
        self._candidate, self._candidate_seen = _detach(row, MAX_CANDIDATE_BYTES), True

    def impressions(self, rows):
        _require(not self._finished and type(rows) is list, "capture_state")
        for row in rows:
            v1._scope(row, self.user_id, self.league_id, self.job_id)
            _size(row)
        compacted, nodes = compact_rows(rows)
        incoming = {}
        for node in nodes:
            _require(node["snapshot_id"] not in incoming, "duplicate_snapshot")
            incoming[node["snapshot_id"]] = node
        reader = self.stage.reader()
        proposed = DiagnosticResolver(_Overlay(reader, incoming), user_id=self.user_id, job_id=self.job_id)
        retained = DiagnosticResolver(reader, user_id=self.user_id, job_id=self.job_id)
        new = []
        for sid, node in incoming.items():
            proposed.validate_node(sid)
            prior = reader.get_nodes([sid]).get(sid)
            if prior is None:
                new.append(node)
            elif prior != node:
                retained.validate_node(sid)
                # Both verified expanded scoped hashes bind the same content.
                _require(all(prior[k] == node[k] for k in ("snapshot_id", "user_id", "deck_job_id")),
                         "snapshot_conflict")
        self.stage.put_nodes(nodes=new)
        for row in compacted:
            self._rows.append(row)
            self._count += 1
            self._ghosts += row.get("is_ghost") == 1

    def finish(self, cards, public_cards, *, significance_by_trade_id=None):
        _require(not self._finished, "capture_state")
        self._rows.flush()
        writer = _PageWriter(self.stage, "cards")
        admission = _PageWriter(self.stage, "admission")
        evidence = (row for _, row in _records(self.stage.reader(), "impressions")
                    if row.get("is_ghost") != 1)
        significance = significance_by_trade_id or {}
        used, earliest, count, absent = set(), None, 0, object()
        for card, public in zip_longest(cards, public_cards, fillvalue=absent):
            _require(card is not absent and public is not absent, "public_count")
            record = v1.capture_runtime_card(card, public, significance=significance.get(card.trade_id))
            row = next(evidence, absent)
            _require(row is not absent, "incomplete_evidence")
            entry = _admission_record(record["runtime"], row["impression_id"], count)
            validate_admission_binding(entry, record, row, ordinal=count)
            writer.append(record)
            admission.append(entry)
            if card.trade_id in significance:
                used.add(card.trade_id)
            if earliest is None or v1._date(card.expires_at) < v1._date(earliest):
                earliest = card.expires_at
            count += 1
        writer.flush()
        admission.flush()
        _require(next(evidence, absent) is absent, "incomplete_evidence")
        _require(used == set(significance), "orphan_significance")
        _require(count + self._ghosts == self._count, "incomplete_evidence")
        self._finished = True
        return {"codec": {"schema": VERSION, "user_id": self.user_id, "league_id": self.league_id,
            "job_id": self.job_id, "card_count": count, "impression_count": self._count,
            "ghost_count": self._ghosts, "expires_at": earliest}, "candidate_set": self._candidate}


def _records(reader, kind):
    ordinal = index = 0
    for page in reader.iter_pages(kind):
        values = page["records"]
        _require(type(values) is list and 0 < len(values) <= MAX_PAGE_RECORDS, "page_records")
        _require(all(type(page[key]) is int for key in ("page_index", "ordinal_start", "ordinal_end")), "page_order")
        _require(page["page_index"] == index and page["ordinal_start"] == ordinal
                 and page["ordinal_end"] == ordinal + len(values), "page_order")
        for value in values:
            _size(value)
            yield ordinal, value
            ordinal += 1
        index += 1


def _card(record, user_id, league_id, now):
    _size(record)
    proof = record.get("owner_evaluation")
    if proof is not None:
        _json(proof["snapshot_json"])
    card = v1.restore_runtime_card(record, user_id=user_id, league_id=league_id)
    if now is not None:
        _require(v1._date(now) < v1._date(card.expires_at), "expired_card")
    return card


def _candidate(row, user_id, league_id, job_id):
    if row is None:
        return None
    _size(row, MAX_CANDIDATE_BYTES)
    _json(row["candidates_json"], MAX_CANDIDATE_BYTES)
    members = v1._candidate(row, user_id=user_id, league_id=league_id, job_id=job_id)
    return ({m["trade_hash"] for m in members if m["in_deck"]},
            {(tuple(m["give"]), tuple(m["receive"]), m["partner"]) for m in members if m["in_deck"]})


def _row(raw, resolver, *, codec, candidate, member_sets, card=None, record=None, ordinal=None):
    required = {"impression_id", "user_id", "league_id", "deck_job_id", "card_index",
                "trade_hash", "features_json", "propensity", "served_at"}
    v1._keys(raw, v1.ROW_FIELDS, required)
    v1._scope(raw, codec["user_id"], codec["league_id"], codec["job_id"])
    v1._text(raw["impression_id"])
    v1._date(raw["served_at"])
    v1._number(raw["propensity"])
    _require(raw["propensity"] >= 0, "propensity")
    for key in ("base_score", "final_score", "fairness_threshold"):
        if raw.get(key) is not None:
            v1._number(raw[key])
    for key in ("arm_rank", "group_rank", "candidate_set_size", "card_index"):
        if raw.get(key) is not None:
            _require(type(raw[key]) is int and raw[key] >= 0, "evidence_count")
    _require(raw.get("is_ghost") in (None, 0, 1) and type(raw.get("is_ghost")) is not bool, "ghost")
    features = resolver.expand(_json(raw["features_json"]))
    _require(type(features) is dict, "features")
    if raw.get("source_like_impression_id") is not None:
        v1._text(raw["source_like_impression_id"])
    valuation = _json(raw["valuation_json"]) if raw.get("valuation_json") is not None else None
    _require(valuation is None or type(valuation) is dict, "valuation")
    assets = _json(raw["assets_json"]) if raw.get("assets_json") is not None else None
    if assets is not None:
        v1._keys(assets, {"give", "receive"}, {"give", "receive"})
        v1._ids(assets["give"])
        v1._ids(assets["receive"])
        _require(not set(assets["give"]) & set(assets["receive"]), "evidence_assets")
        v1._text(features.get("partner_user_id"))
        _require(raw["trade_hash"] == v1._trade_hash(assets["give"], assets["receive"], features["partner_user_id"]), "evidence_terms")
    if candidate is not None:
        _require(raw.get("candidate_set_id") == candidate["candidate_set_id"]
                 and raw.get("candidate_set_size") == candidate["size"]
                 and raw["trade_hash"] in member_sets[0], "candidate_link")
        _require(assets is not None and (tuple(assets["give"]), tuple(assets["receive"]), features.get("partner_user_id")) in member_sets[1], "candidate_terms")
    else:
        _require(raw.get("candidate_set_id") is None and raw.get("candidate_set_size") is None, "missing_candidate")
    if card is not None:
        _require(raw.get("is_ghost") != 1 and raw["card_index"] == ordinal, "evidence_order")
        _require(raw["trade_hash"] == v1._trade_hash(card.give_player_ids, card.receive_player_ids, card.target_user_id), "evidence_terms")
        _require(features.get("partner_user_id") == card.target_user_id, "evidence_partner")
        _require(raw.get("source_like_impression_id") == card.source_like_impression_id, "source_link")
        _require(record["public"].get("impression_id", raw["impression_id"]) == raw["impression_id"], "public_impression")
        if assets is not None:
            _require(assets == {"give": card.give_player_ids, "receive": card.receive_player_ids}, "evidence_assets")
        owner_proof = getattr(card, "owner_evaluation", None)
        if owner_proof is not None:
            proof = owner_proof.as_dict()
            _require(v1._canonical(valuation) == v1._canonical(proof), "evidence_proof")
            _require(raw.get("model_arm") == proof["generator"], "evidence_model")
    return {**raw, "features_json": features}


def _admission_record(runtime, impression_id, ordinal):
    return {"ordinal": ordinal, "impression_id": impression_id,
            **{key: runtime[key] for key in ADMISSION_FIELDS - {"ordinal", "impression_id"}}}


def _admission_entry(entry, *, ordinal, user_id, now=None):
    _size(entry)
    v1._keys(entry, ADMISSION_FIELDS, ADMISSION_FIELDS)
    _require(type(entry["ordinal"]) is int and entry["ordinal"] == ordinal, "admission_order")
    for key in ("trade_id", "target_user_id", "impression_id"):
        v1._text(entry[key])
    _require(entry["target_user_id"] != user_id, "admission_self_trade")
    give, receive = v1._ids(entry["give_player_ids"]), v1._ids(entry["receive_player_ids"])
    _require(not set(give) & set(receive), "admission_assets")
    _require(type(entry["likes_you"]) is bool, "admission_boolean")
    if entry["standing_offer_reason"] is not None:
        v1._text(entry["standing_offer_reason"], empty=True)
    if entry["source_like_impression_id"] is not None:
        v1._text(entry["source_like_impression_id"])
        _require(entry["likes_you"], "admission_source_without_interest")
    expiry = v1._date(entry["expires_at"])
    if now is not None:
        _require(v1._date(now) < expiry, "expired_card")
    return entry


def validate_admission_binding(entry, record, row, *, ordinal, now=None):
    """Bind an authenticated compact entry to its exact original native pair.

    The publisher still restores the native proof and complete evidence. The
    authoritative store may use this on its re-read, root-authenticated pair
    without re-evaluating or re-parsing the immutable native proof.
    """
    runtime = record["runtime"]
    _admission_entry(entry, ordinal=ordinal, user_id=runtime["proposing_user_id"], now=now)
    expected = _admission_record(runtime, row["impression_id"], ordinal)
    _require(v1._canonical(entry) == v1._canonical(expected), "admission_binding")
    _require(row.get("is_ghost") != 1 and type(row["card_index"]) is int
             and row["card_index"] == ordinal, "admission_evidence_order")


@dataclass(frozen=True)
class DispositionCard:
    """Only authenticated disposition inputs; never a publishable TradeCard."""
    ordinal: int
    trade_id: str
    give_player_ids: tuple[str, ...]
    receive_player_ids: tuple[str, ...]
    target_user_id: str
    likes_you: bool
    standing_offer_reason: str | None
    source_like_impression_id: str | None
    impression_id: str
    expires_at: str


def _inventory_context(reader, *, user_id, league_id, now):
    metadata, header = reader.metadata(), reader.header
    codec, candidate = metadata["codec"], metadata["candidate_set"]
    keys = {"schema", "user_id", "league_id", "job_id", "card_count", "impression_count", "ghost_count", "expires_at"}
    v1._keys(codec, keys, keys)
    _require(codec["schema"] == VERSION and codec["user_id"] == user_id and codec["league_id"] == league_id, "scope")
    v1._text(codec["job_id"])
    _require(type(header["schema_version"]) is int and header["schema_version"] == 2 and header["scope"]["user_id"] == user_id
             and header["scope"]["league_id"] == league_id, "scope")
    for key in ("card_count", "impression_count", "ghost_count"):
        _require(type(codec[key]) is int and codec[key] >= 0 and type(header[key]) is int
                 and header[key] == codec[key], "count")
    v1._date(header["expires_at"])
    if now is not None:
        _require(v1._date(now) < v1._date(header["expires_at"]), "expired_inventory")
    member_sets = _candidate(candidate, user_id, league_id, codec["job_id"])
    return metadata, header, codec, candidate, member_sets


def restore_inventory(reader, *, user_id, league_id, now):
    """Full bounded semantic preflight; mandatory for the store's pinned seal."""
    _, header, codec, candidate, member_sets = _inventory_context(
        reader, user_id=user_id, league_id=league_id, now=now)
    resolver = DiagnosticResolver(reader, user_id=user_id, job_id=codec["job_id"])
    node_ids = set()
    for page in reader.iter_node_pages():
        for node in page:
            sid = node["snapshot_id"]
            _require(sid not in node_ids, "duplicate_snapshot")
            node_ids.add(sid)
            resolver.validate_node(sid)
    del node_ids
    cards = iter(_records(reader, "cards"))
    admission = iter(_records(reader, "admission"))
    card_ids, impression_ids = set(), set()
    count = ghosts = total = 0
    earliest = None
    for _, raw in _records(reader, "impressions"):
        v1._text(raw.get("impression_id"))
        _require(raw["impression_id"] not in impression_ids, "duplicate_impression")
        impression_ids.add(raw["impression_id"])
        total += 1
        if raw.get("is_ghost") == 1:
            _row(raw, resolver, codec=codec, candidate=candidate, member_sets=member_sets)
            ghosts += 1
            continue
        item = next(cards, None)
        _require(item is not None, "incomplete_evidence")
        ordinal, record = item
        indexed = next(admission, None)
        _require(indexed is not None and indexed[0] == ordinal, "admission_count")
        validate_admission_binding(indexed[1], record, raw, ordinal=ordinal, now=now)
        card = _card(record, user_id, league_id, now)
        _require(card.trade_id not in card_ids, "duplicate_trade_id")
        card_ids.add(card.trade_id)
        _row(raw, resolver, codec=codec, candidate=candidate, member_sets=member_sets,
             card=card, record=record, ordinal=ordinal)
        if earliest is None or v1._date(card.expires_at) < v1._date(earliest):
            earliest = card.expires_at
        count += 1
    _require(next(cards, None) is None and next(admission, None) is None and (count, total, ghosts) == (
        codec["card_count"], codec["impression_count"], codec["ghost_count"]), "incomplete_evidence")
    _require(earliest == codec["expires_at"], "expiry_binding")
    return PagedPreparedInventory(reader, codec, candidate, earliest or header["expires_at"], now)


class CurrentDispositionMismatch(Exception):
    """Current activity does not permit reuse; the sealed artifact is not corrupt."""


def open_attested_inventory(reader, *, user_id, league_id, now, disposition_check=None):
    """Fast sealed admission, never an alternative way to mint validation.

    Only the trusted store Reader implements verified_attestation: it rejects
    absent/unknown reserved receipts and binds validator identity, frozen tree,
    header, metadata and counts. A metadata 'validated' flag has no authority.
    Native proofs/diagnostics remain mandatory at each publishing batch.
    Optional read-only disposition_check receives at most100 immutable objects
    during this same complete index scan. Only explicit True permits reuse;
    another result is a current-state miss, never evidence of stored corruption.
    """
    _require(reader is not None and callable(getattr(reader, "metadata", None)), "missing_reader")
    _, header, codec, candidate, _ = _inventory_context(
        reader, user_id=user_id, league_id=league_id, now=now)
    verify = getattr(reader, "verified_attestation", None)
    _require(callable(verify), "missing_attestation")
    attestation = verify(codec_version=VERSION, validator_version=VALIDATOR_VERSION)
    _require(type(attestation) is dict and attestation.get("codec_version") == VERSION
             and attestation.get("validator_version") == VALIDATOR_VERSION
             and attestation.get("root_sha256") == header["root_sha256"], "invalid_attestation")
    inventory = PagedPreparedInventory(reader, codec, candidate,
        codec["expires_at"] or header["expires_at"], now)
    trades, impressions, earliest, count = set(), set(), None, 0
    pending = []

    def check_current():
        if disposition_check(tuple(pending)) is not True:
            raise CurrentDispositionMismatch("current dispositions do not permit prepared reuse")
        pending.clear()

    for card in inventory.iter_disposition_cards():
        _require(card.trade_id not in trades and card.impression_id not in impressions,
                 "duplicate_admission_identity")
        trades.add(card.trade_id)
        impressions.add(card.impression_id)
        if earliest is None or v1._date(card.expires_at) < v1._date(earliest):
            earliest = card.expires_at
        count += 1
        if disposition_check is not None:
            pending.append(card)
            if len(pending) == MAX_PAGE_RECORDS:
                check_current()
    _require(count == codec["card_count"] and earliest == codec["expires_at"], "admission_count_or_expiry")
    if pending:
        check_current()
    inventory._current()
    return inventory


class PagedPreparedInventory:
    def __init__(self, reader, codec, candidate, expires_at, now):
        self.reader, self.codec, self.candidate_set = reader, codec, candidate
        self.card_count, self.ghost_count = codec["card_count"], codec["ghost_count"]
        self.expires_at, self.now = expires_at, now
        self._root = reader.header["root_sha256"]

    def _current(self):
        _require(self.reader.header["root_sha256"] == self._root, "inventory_changed")

    def iter_cards(self):
        self._current()
        for _, record in _records(self.reader, "cards"):
            yield _card(record, self.codec["user_id"], self.codec["league_id"], self.now)

    def iter_disposition_cards(self):
        self._current()
        count = 0
        for ordinal, entry in _records(self.reader, "admission"):
            _admission_entry(entry, ordinal=ordinal, user_id=self.codec["user_id"], now=self.now)
            yield DispositionCard(**{**entry, "give_player_ids": tuple(entry["give_player_ids"]),
                "receive_player_ids": tuple(entry["receive_player_ids"])})
            count += 1
        _require(count == self.card_count, "admission_count")

    def batches(self, *, served_at, trade_ids=None, first_batch_size=30, batch_size=100,
                first_deck=False, board_state=None):
        self._current()
        v1._date(served_at)
        _require(type(served_at) is str and type(first_deck) is bool, "publication")
        _require(all(type(size) is int and 0 < size <= MAX_PAGE_RECORDS for size in (first_batch_size, batch_size)), "batch_size")
        if trade_ids is not None:
            v1._ids(trade_ids, empty=True)
            _require(all(left == right for left, right in zip_longest(trade_ids, (c.trade_id for c in self.iter_cards()))), "full_inventory_required")
        if board_state is not None:
            _require(type(board_state) in (list, tuple) and len(board_state) == 2
                     and type(board_state[0]) is int and board_state[0] >= 0, "board_state")
            if board_state[1] is not None:
                v1._date(board_state[1])
        cursor, first = {"cards": 0, "ghosts": 0}, True
        members = _candidate(self.candidate_set, self.codec["user_id"], self.codec["league_id"], self.codec["job_id"])
        def package(entries, ghosts=False):
            nonlocal first, cursor
            # A detached verified page may be retained across a yield. The
            # evidence writer must reread its authoritative original slice
            # before commitment; this iterator does not publish anything.
            self._current()
            before = dict(cursor)
            cards, public, rows, records, significance = [], [], [], {}, {}
            for card, record, row in entries:
                row["served_at"] = served_at
                if not ghosts:
                    row["card_index"] = cursor["cards"]
                    features = row["features_json"]
                    features.pop("first_deck", None)
                    if first_deck:
                        features["first_deck"] = True
                    if board_state is not None:
                        features.update(ranked_player_count=board_state[0], last_board_update_at=board_state[1],
                                        user_value_basis="personal" if board_state[0] else "consensus")
                    cards.append(card)
                    public.append({**_detach(record["public"]), "impression_id": row["impression_id"]})
                    records[card.trade_id] = record
                    if record["significance"] is not None:
                        value = record["significance"]
                        significance[card.trade_id] = (value[0], tuple(value[1]), tuple(value[2]))
                    cursor["cards"] += 1
                else:
                    cursor["ghosts"] += 1
                rows.append(row)
            result = {"cards": cards, "public_cards": public, "impression_rows": rows,
                "candidate_set": _detach(self.candidate_set, MAX_CANDIDATE_BYTES) if first else None,
                "runtime_records": records, "significance_by_trade_id": significance,
                "cursor_before": before, "cursor_after": dict(cursor)}
            first = False
            return result
        for ghosts in (False, True):
            if ghosts and not self.ghost_count:
                continue
            card_stream = iter(_records(self.reader, "cards")) if not ghosts else None
            admission_stream = iter(_records(self.reader, "admission")) if not ghosts else None
            resolver = DiagnosticResolver(self.reader, user_id=self.codec["user_id"], job_id=self.codec["job_id"])
            entries, size = [], 0
            for _, raw in _records(self.reader, "impressions"):
                if (raw.get("is_ghost") == 1) != ghosts:
                    continue
                card = record = ordinal = None
                if not ghosts:
                    native = next(card_stream, None)
                    _require(native is not None, "incomplete_evidence")
                    ordinal, record = native
                    card = _card(record, self.codec["user_id"], self.codec["league_id"], served_at)
                    indexed = next(admission_stream, None)
                    _require(indexed is not None and indexed[0] == ordinal, "admission_count")
                    validate_admission_binding(indexed[1], record, raw, ordinal=ordinal, now=served_at)
                row = _row(raw, resolver, codec=self.codec, candidate=self.candidate_set,
                    member_sets=members, card=card, record=record, ordinal=ordinal)
                used = _size(row, MAX_BATCH_BYTES) + (_size(record) if record is not None else 0)
                _require(used <= MAX_BATCH_BYTES, "batch_record_bytes")
                limit = first_batch_size if first else batch_size
                if entries and (size + used > MAX_BATCH_BYTES or len(entries) >= limit):
                    yield package(entries, ghosts)
                    entries, size = [], 0
                    resolver = DiagnosticResolver(self.reader, user_id=self.codec["user_id"], job_id=self.codec["job_id"])
                    self._current()
                entries.append((card, record, row))
                size += used
            if entries:
                self._current()
                yield package(entries, ghosts)
        if first:
            _require(self.card_count == 0 and self.ghost_count == 0, "incomplete_evidence")
            self._current()
            yield package([])
        _require(cursor == {"cards": self.card_count, "ghosts": self.ghost_count},
                 "incomplete_evidence")


def adoption_projection(reader, *, card_start, card_end, ghost_start, ghost_end):
    """Authenticated bounded original slice for the store's exact v1 binder."""
    metadata = reader.metadata()
    codec = metadata["codec"]
    cards = reader.read_cards(card_start, card_end)
    impressions = [*reader.read_impressions(card_start, card_end),
                   *reader.read_impressions(ghost_start, ghost_end, ghosts=True)]
    _size(cards, MAX_BATCH_BYTES)
    _size(impressions, MAX_BATCH_BYTES)
    resolver = DiagnosticResolver(reader, user_id=codec["user_id"], job_id=codec["job_id"])
    nodes = resolver.closure(_json(row["features_json"]) for row in impressions)
    return {"schema": v1.VERSION, "user_id": codec["user_id"], "league_id": codec["league_id"],
            "job_id": codec["job_id"], "cards": cards, "impressions": impressions,
            "snapshots": nodes, "candidate_set": metadata["candidate_set"]}
