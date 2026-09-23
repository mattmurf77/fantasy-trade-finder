"""Private bounded prepared inventories, authorized by the chunked-storage plan.

Staging is deletion-indexed before private writes and frozen before validation.
Only a complete validated manifest becomes active. No generator, server,
provider, or activity imports; no binary object deserialization.
"""
from contextlib import contextmanager
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
import base64
import binascii
import hashlib
import uuid
import zlib

from sqlalchemy import bindparam, delete, func, insert, or_, select, update

from . import database as db, prepared_trade_store as v1, user_data_lifecycle

InvalidArtifact, StaleWork = v1.InvalidArtifact, v1.StaleWork
SCHEMA_VERSION = 2
MAX_PAGE_LOGICAL_BYTES = 4 * 1024 * 1024
MAX_PAGE_ENCODED_BYTES = 768 * 1024
MAX_PAGE_RECORDS = 100
MAX_SQL_STATEMENT_BYTES = 2 * 1024 * 1024
PREFIX = "prepared-page-zlib-2:"
KINDS = frozenset({"cards", "impressions", "admission"})
ATTESTATION_KEY = "__semantic_attestation"
ATTESTATION_VERSION = "prepared-semantic-attestation-1"
SUBJECT_KIND = "inventory_v2"
M = db.prepared_trade_manifests_v2_table
P = db.prepared_trade_pages_v2_table
N = db.prepared_trade_nodes_v2_table


def _hash(raw):
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _encode(value):
    from .prepared_trade_payload_v2 import _size
    try:
        _size(value, MAX_PAGE_LOGICAL_BYTES)
    except ValueError as exc:
        raise InvalidArtifact("prepared page exceeds structural budget") from exc
    raw = v1._encode(value)
    size = len(raw.encode("utf-8"))
    if size > MAX_PAGE_LOGICAL_BYTES:
        raise v1._invalid_measured("prepared page exceeds logical byte limit",
            logical_bytes=size, logical_limit_bytes=MAX_PAGE_LOGICAL_BYTES)
    packed = PREFIX + base64.b64encode(zlib.compress(raw.encode("utf-8"), 6)).decode("ascii")
    if len(packed) > MAX_PAGE_ENCODED_BYTES:
        raise v1._invalid_measured("prepared page exceeds encoded byte limit",
            logical_bytes=size, encoded_bytes=len(packed), encoded_limit_bytes=MAX_PAGE_ENCODED_BYTES)
    return {"payload_json": packed, "payload_sha256": _hash(raw),
            "logical_bytes": size, "encoded_bytes": len(packed)}


def _unpack(packed, digest):
    if (type(packed) is not str or len(packed) > MAX_PAGE_ENCODED_BYTES or not packed.startswith(PREFIX)
            or len(packed.encode("utf-8")) > MAX_PAGE_ENCODED_BYTES):
        raise InvalidArtifact("invalid bounded prepared encoding")
    try:
        dec = zlib.decompressobj()
        raw = dec.decompress(base64.b64decode(packed[len(PREFIX):], validate=True), MAX_PAGE_LOGICAL_BYTES + 1)
        if len(raw) > MAX_PAGE_LOGICAL_BYTES or not dec.eof or dec.unused_data or dec.unconsumed_tail:
            raise InvalidArtifact("invalid bounded prepared compression")
        text = raw.decode("utf-8")
        if _hash(text) != digest:
            raise InvalidArtifact("prepared checksum mismatch")
        return text
    except (binascii.Error, zlib.error, UnicodeError) as exc:
        raise InvalidArtifact("invalid bounded prepared compression") from exc


def _decode(row):
    if (type(row["logical_bytes"]) is not int or not 0 <= row["logical_bytes"] <= MAX_PAGE_LOGICAL_BYTES
            or type(row["encoded_bytes"]) is not int or row["encoded_bytes"] != len(row["payload_json"])):
        raise InvalidArtifact("invalid bounded prepared sizes")
    raw = _unpack(row["payload_json"], row["payload_sha256"])
    if len(raw.encode("utf-8")) != row["logical_bytes"]:
        raise InvalidArtifact("prepared logical size mismatch")
    return _parse(raw)


def _parse(raw):
    from .prepared_trade_payload_v2 import _json
    try:
        return _json(raw, MAX_PAGE_LOGICAL_BYTES)
    except ValueError as exc:
        raise InvalidArtifact("prepared page exceeds structural budget") from exc


def _text_pair(value):
    encoded = _encode(value)
    return encoded["payload_json"], encoded["payload_sha256"]


def sql_bytes(rows):
    """Conservative execute/executemany bound, including escaping and syntax.

    Twice UTF-8 bytes bounds text-protocol quote/backslash escaping. Per-scalar
    overhead and 4096 syntax bytes exceed these fixed insert/update statements.
    """
    total = 4096
    for row in rows:
        for key, value in row.items():
            total += 64 + 2 * len(str(key).encode("utf-8"))
            if value is not None:
                total += 2 * len((value if type(value) is str else str(value)).encode("utf-8"))
    return total


def _sql_chunks(rows):
    chunk, size = [], 4096
    for row in rows:
        added = sql_bytes([row]) - 4096
        if added + 4096 > MAX_SQL_STATEMENT_BYTES:
            raise v1._invalid_measured("prepared SQL statement exceeds byte limit; nothing truncated",
                encoded_bytes=added + 4096, encoded_limit_bytes=MAX_SQL_STATEMENT_BYTES)
        if chunk and (len(chunk) >= MAX_PAGE_RECORDS or size + added > MAX_SQL_STATEMENT_BYTES):
            yield chunk
            chunk, size = [], 4096
        chunk.append(row)
        size += added
    if chunk:
        yield chunk


def _write(conn, table, rows):
    for chunk in _sql_chunks(rows):
        conn.execute(insert(table), chunk)


def _update(conn, stmt, values):
    list(_sql_chunks([values]))
    return conn.execute(stmt.values(**values))


def _descriptor(kind, row):
    fields = ("inventory_id", "payload_sha256", "logical_bytes", "encoded_bytes")
    fields += (("snapshot_id",) if kind == "node" else ("kind", "page_index", "ordinal_start",
               "ordinal_end", "real_start", "real_end", "ghost_start", "ghost_end"))
    return {"type": kind, **{key: row[key] for key in fields}}


def _leaf(kind, row):
    return _hash("leaf\n" + v1._encode(_descriptor(kind, row)))


def _pair(left, right):
    return _hash("pair\n" + left + right)


def _proof_check(kind, row, tree):
    value = _leaf(kind, row)
    raw = row["proof_json"]
    if type(raw) is not str or len(raw) > 16384 or len(raw.encode("utf-8")) > 16384:
        raise InvalidArtifact("invalid prepared root proof")
    proof = _parse(raw)
    if type(proof) is not list or len(proof) > 64:
        raise InvalidArtifact("invalid prepared root proof")
    for entry in proof:
        if (type(entry) is not list or len(entry) != 2 or type(entry[0]) is not bool
                or type(entry[1]) is not str or len(entry[1]) != 64):
            raise InvalidArtifact("invalid prepared root proof")
        value = _pair(entry[1], value) if entry[0] else _pair(value, entry[1])
    if value != tree:
        raise InvalidArtifact("prepared page differs from sealed root")


def _manifest_root(row):
    return v1.dependency_hash({key: row[key] for key in (
        "inventory_id", "header_sha256", "metadata_sha256", "tree_sha256", "card_count",
        "impression_count", "ghost_count", "node_count", "page_count")})


@lru_cache(maxsize=1)
def _validator_source_sha256():
    # Code is process-static in production. The runtime independently compares
    # the entire current model/source receipt before accepting this artifact.
    from . import prepared_trade_payload_v2 as codec
    return hashlib.sha256(Path(codec.__file__).read_bytes()).hexdigest()


def _attestation(row, original_metadata_sha256):
    from . import prepared_trade_payload_v2 as codec
    semantic = {**row, "metadata_sha256": original_metadata_sha256}
    return {"version": ATTESTATION_VERSION, "codec_version": codec.VERSION,
        "validator_version": codec.VALIDATOR_VERSION,
        "validator_source_sha256": _validator_source_sha256(),
        "header_sha256": row["header_sha256"], "metadata_sha256": original_metadata_sha256,
        "tree_sha256": row["tree_sha256"], "validated_root_sha256": _manifest_root(semantic),
        "counts": {key: row[key] for key in ("card_count", "impression_count", "ghost_count", "page_count", "node_count")}}


def _header(row):
    data = _parse(_unpack(row["header_json"], row["header_sha256"]))
    if (type(data) is not dict or type(data.get("schema_version")) is not int or data["schema_version"] != SCHEMA_VERSION
            or v1._scope(data["scope"]).key != row["scope_key"]
            or data["scope"]["user_id"] != row["user_id"] or data["scope"]["league_id"] != row["league_id"]
            or data["created_at"] != row["created_at"] or data["expires_at"] != row["expires_at"]
            or v1._participants(v1._scope(data["scope"]), data["participants"]) != data["participants"]):
        raise InvalidArtifact("invalid prepared manifest binding")
    created, expiry = v1._time(data["created_at"]), v1._time(data["expires_at"])
    if not created < expiry <= created + v1.MAX_RETENTION:
        raise InvalidArtifact("invalid prepared manifest expiry")
    if (row["state"] in ("sealed", "validating") and row["root_sha256"] != _manifest_root(row)
            or row["state"] == "sealed" and row["active_scope_key"] != row["scope_key"]):
        raise InvalidArtifact("invalid sealed prepared root")
    publication = None
    if row["adoption_json"] is not None:
        publication = _parse(_unpack(row["adoption_json"], row["adoption_sha256"]))
        if type(publication) is not dict:
            raise InvalidArtifact("invalid prepared publication")
    elif row["adoption_sha256"] is not None:
        raise InvalidArtifact("invalid prepared publication checksum")
    for key in ("card_count", "impression_count", "ghost_count", "node_count", "page_count",
                "adoption_prefix", "adoption_ghost_prefix"):
        if type(row[key]) is not int or row[key] < 0:
            raise InvalidArtifact("invalid prepared manifest count")
    if row["adoption_prefix"] > row["card_count"] or row["adoption_ghost_prefix"] > row["ghost_count"]:
        raise InvalidArtifact("invalid prepared publication cursor")
    return {**data, "inventory_id": row["inventory_id"], "state": row["state"],
        "root_sha256": row["root_sha256"], "tree_sha256": row["tree_sha256"],
        **{key: row[key] for key in ("card_count", "impression_count", "ghost_count", "node_count", "page_count")},
        "published_count": row["adoption_prefix"], "ghost_published_count": row["adoption_ghost_prefix"],
        "publication": publication}


def _index_matches(conn, header):
    table = db.prepared_trade_participants_table
    actual = sorted(conn.execute(select(table.c.participant_user_id, table.c.user_id).where(
        table.c.subject_kind == SUBJECT_KIND, table.c.subject_id == header["inventory_id"])).all())
    return actual == [(uid, header["scope"]["user_id"]) for uid in header["participants"]]


class Reader:
    def __init__(self, inventory_id, *, staging=False, root=None, stage=None):
        self.inventory_id, self.staging, self.root = inventory_id, staging, root
        self.stage = stage

    def _heartbeat(self):
        if self.stage is not None and v1._time() >= self.stage.renew_at:
            with _stage_work(self.stage, None, allowed=("staging", "validating")):
                pass

    def _row(self, conn):
        row = conn.execute(select(M).where(M.c.inventory_id == self.inventory_id)).mappings().first()
        allowed = ("staging", "validating") if self.staging else ("sealed",)
        if not row or row["state"] not in allowed:
            raise StaleWork("prepared inventory no longer active")
        if self.root is not None and row["root_sha256"] != self.root:
            raise StaleWork("prepared inventory root changed")
        if (row["state"] in ("sealed", "validating") and row["root_sha256"] != _manifest_root(row)
                or row["state"] == "sealed" and row["active_scope_key"] != row["scope_key"]):
            raise InvalidArtifact("invalid sealed prepared root")
        return row

    @property
    def header(self):
        with db.engine.connect() as conn:
            return _header(self._row(conn))

    def metadata(self):
        with db.engine.connect() as conn:
            row = self._row(conn)
            if row["metadata_json"] is None:
                raise InvalidArtifact("prepared metadata not finished")
            value = _parse(_unpack(row["metadata_json"], row["metadata_sha256"]))
            if type(value) is not dict:
                raise InvalidArtifact("invalid prepared metadata")
            return value

    def verified_attestation(self, *, codec_version, validator_version):
        """Verify a store-minted attestation, not a caller's validated boolean.

        SHA bindings give integrity under the trusted store/DB writer contract,
        not authentication against an administrator replacing the database.
        """
        from . import prepared_trade_payload_v2 as codec
        if (self.staging or type(codec_version) is not str or type(validator_version) is not str
                or codec_version != codec.VERSION or validator_version != codec.VALIDATOR_VERSION):
            raise InvalidArtifact("unsupported prepared semantic attestation")
        with db.engine.connect() as conn:
            row = self._row(conn)
            metadata = _parse(_unpack(row["metadata_json"], row["metadata_sha256"]))
            if type(metadata) is not dict:
                raise InvalidArtifact("invalid prepared semantic attestation")
            attestation = metadata.pop(ATTESTATION_KEY, None)
            if type(attestation) is not dict:
                raise InvalidArtifact("missing prepared semantic attestation")
            original_sha = _hash(v1._encode(metadata))
            expected = _attestation(row, original_sha)
            if v1.dependency_hash(attestation) != v1.dependency_hash(expected):
                raise InvalidArtifact("invalid prepared semantic attestation")
            return {**attestation, "root_sha256": row["root_sha256"]}

    def _part(self, kind, row, manifest):
        if manifest["state"] in ("sealed", "validating"):
            _proof_check(kind, row, manifest["tree_sha256"])
        return _decode(row)

    def iter_pages(self, kind, start_ordinal=0):
        if kind not in KINDS or type(start_ordinal) is not int or start_ordinal < 0:
            raise InvalidArtifact("invalid prepared page selection")
        cursor = -1
        while True:
            self._heartbeat()
            with db.engine.connect() as conn:
                manifest = self._row(conn)
                row = conn.execute(select(P).where(P.c.inventory_id == self.inventory_id,
                    P.c.kind == kind, P.c.page_index > cursor, P.c.ordinal_end > start_ordinal)
                    .order_by(P.c.page_index).limit(1)).mappings().first()
                if row is None:
                    return
                records = self._part("page", row, manifest)
                if (type(records) is not list or not 0 < len(records) <= MAX_PAGE_RECORDS
                        or row["ordinal_end"] - row["ordinal_start"] != len(records)):
                    raise InvalidArtifact("invalid prepared page record count")
                cursor = row["page_index"]
                result = {key: row[key] for key in ("page_index", "ordinal_start", "ordinal_end",
                    "real_start", "real_end", "ghost_start", "ghost_end")}
                result["records"] = records
            yield result

    def _read_range(self, kind, start, end, ghosts=False):
        if type(start) is not int or type(end) is not int or not 0 <= start <= end or end - start > MAX_PAGE_RECORDS:
            raise InvalidArtifact("invalid bounded prepared range")
        if start == end:
            return []
        prefix = "ordinal" if kind in ("cards", "admission") else ("ghost" if ghosts else "real")
        result, cursor, measured = [], -1, 0
        while len(result) < end - start:
            self._heartbeat()
            with db.engine.connect() as conn:
                manifest = self._row(conn)
                row = conn.execute(select(P).where(P.c.inventory_id == self.inventory_id,
                    P.c.kind == kind, P.c.page_index > cursor, P.c[prefix + "_end"] > start,
                    P.c[prefix + "_start"] < end).order_by(P.c.page_index).limit(1)).mappings().first()
                if row is None:
                    raise InvalidArtifact("missing prepared range")
                values = self._part("page", row, manifest)
                if kind == "impressions":
                    values = [value for value in values if (value.get("is_ghost") == 1) == ghosts]
                base = row[prefix + "_start"]
                selection = values[max(0, start - base):min(len(values), end - base)]
                from .prepared_trade_payload_v2 import _size, MAX_BATCH_BYTES
                for record in selection:
                    measured += _size(record)
                    if measured > MAX_BATCH_BYTES:
                        raise InvalidArtifact("prepared bounded range exceeds byte limit")
                    result.append(record)
                cursor = row["page_index"]
        if len(result) != end - start:
            raise InvalidArtifact("prepared range overlaps")
        return result

    def read_cards(self, start, end):
        return self._read_range("cards", start, end)

    def read_admission(self, start, end):
        return self._read_range("admission", start, end)

    def read_impressions(self, start, end, ghosts=False):
        return self._read_range("impressions", start, end, ghosts)

    def get_nodes(self, snapshot_ids):
        ids = list(snapshot_ids)
        if len(ids) > MAX_PAGE_RECORDS or any(type(key) is not str or len(key) != 64 for key in ids):
            raise InvalidArtifact("invalid bounded diagnostic selection")
        self._heartbeat()
        result, measured = {}, 0
        with db.engine.connect() as conn:
            manifest = self._row(conn)
            for key in ids:
                row = conn.execute(select(N).where(N.c.inventory_id == self.inventory_id,
                    N.c.snapshot_id == key)).mappings().first()
                if row is not None:
                    measured += row["logical_bytes"]
                    if measured > MAX_PAGE_LOGICAL_BYTES:
                        raise InvalidArtifact("prepared node selection exceeds byte limit")
                    result[key] = self._part("node", row, manifest)
        return result

    def iter_node_pages(self):
        cursor = ""
        while True:
            self._heartbeat()
            with db.engine.connect() as conn:
                manifest = self._row(conn)
                row = conn.execute(select(N).where(N.c.inventory_id == self.inventory_id,
                    N.c.snapshot_id > cursor).order_by(N.c.snapshot_id).limit(1)).mappings().first()
                if row is None:
                    return
                value = self._part("node", row, manifest)
                cursor = row["snapshot_id"]
            yield [value]


class Stage:
    def __init__(self, inventory_id, claim):
        self.inventory_id, self.claim = inventory_id, v1._decode(v1._encode(claim))
        self.renew_at = v1._time() + timedelta(seconds=60)

    def reader(self):
        return Reader(self.inventory_id, staging=True, stage=self,
                      root=getattr(self, "validation_root", None))

    def append_page(self, kind, page_index, ordinal_start, records, **kwargs):
        return append_page(self, kind=kind, page_index=page_index, ordinal_start=ordinal_start, records=records, **kwargs)

    def put_nodes(self, nodes, **kwargs):
        return put_nodes(self, nodes=nodes, **kwargs)

    def finish_metadata(self, metadata, **kwargs):
        return finish_metadata(self, metadata=metadata, **kwargs)


@contextmanager
def _stage_work(stage, now, allowed=("staging",)):
    claim = stage.claim
    list(_sql_chunks([{str(i): uid for i, uid in enumerate(claim["participants"])}]))
    with v1._work(claim["participants"], claim["work_started"]), db.engine.begin() as conn:
        identities = v1._identity_receipt(conn, claim["participants"], claim["scope"]["user_id"])
        target, original = v1._claimed(conn, claim, v1._iso(now))
        if v1.dependency_hash(identities) != v1.dependency_hash(original["identity_receipt"]):
            raise StaleWork("prepared participant lifetime changed")
        row = conn.execute(select(M).where(M.c.inventory_id == stage.inventory_id,
            M.c.state.in_(allowed), M.c.target_id == claim["target_id"],
            M.c.generation_token == claim["lease_token"], M.c.expires_at > v1._iso(now))
            .with_for_update()).mappings().first()
        if row is None or not _index_matches(conn, _header(row)):
            raise StaleWork("prepared stage changed, expired or was deleted")
        current = v1._time(now)
        if v1._time(target["lease_until"]) - current < timedelta(seconds=120):
            until = v1._iso(min(current + timedelta(seconds=300), v1._time(row["expires_at"])))
            conn.execute(update(db.prepared_trade_targets_table).where(
                db.prepared_trade_targets_table.c.target_id == claim["target_id"],
                db.prepared_trade_targets_table.c.lease_token == claim["lease_token"]).values(lease_until=until))
            conn.execute(update(db.prepared_trade_worker_table).where(
                db.prepared_trade_worker_table.c.worker_id == 1,
                db.prepared_trade_worker_table.c.lease_token == claim["lease_token"]).values(lease_until=until))
        stage.renew_at = current + timedelta(seconds=60)
        yield conn, row


def begin_inventory(claim, *, dependency_receipt, model_identity, participants,
                    created_at, expires_at, now=None):
    scope = v1._scope(claim["scope"])
    participants = v1._participants(scope, participants)
    if participants != claim["participants"]:
        raise StaleWork("all consumed participants must be bound before generation")
    created, expiry = v1._time(created_at), v1._time(expires_at)
    if created > v1._time(now) or not v1._time(now) < expiry <= created + v1.MAX_RETENTION:
        raise InvalidArtifact("inventory expiry must be original, future, and at most 24 hours")
    if type(dependency_receipt) is not dict or not dependency_receipt or type(model_identity) is not dict or not model_identity:
        raise InvalidArtifact("explicit nonempty dependency/model receipts required")
    data = {"schema_version": SCHEMA_VERSION, "scope": scope.as_dict(), "participants": participants,
        "dependency_receipt": dependency_receipt, "model_identity": model_identity,
        "identity_receipt": claim["identity_receipt"], "created_at": v1._iso(created), "expires_at": v1._iso(expiry)}
    packed, digest = _text_pair(data)
    list(_sql_chunks([{str(i): uid for i, uid in enumerate(participants)}]))
    inventory_id = uuid.uuid4().hex
    with v1._work(participants, claim["work_started"]), db.engine.begin() as conn:
        identities = v1._identity_receipt(conn, participants, scope.user_id)
        _, original = v1._claimed(conn, claim, v1._iso(now))
        if v1.dependency_hash(identities) != v1.dependency_hash(original["identity_receipt"]):
            raise StaleWork("prepared participant lifetime changed")
        v1._index(conn, SUBJECT_KIND, inventory_id, scope.user_id, participants)
        _write(conn, M, [dict(inventory_id=inventory_id, scope_key=scope.key, user_id=scope.user_id,
            league_id=scope.league_id, state="staging", target_id=claim["target_id"],
            generation_token=claim["lease_token"], created_at=data["created_at"], expires_at=data["expires_at"],
            header_json=packed, header_sha256=digest)])
    return Stage(inventory_id, claim)


def append_page(stage, *, kind, page_index, ordinal_start, records, now=None):
    if (kind not in KINDS or type(page_index) is not int or page_index < 0
            or type(ordinal_start) is not int or ordinal_start < 0
            or type(records) is not list or not 0 < len(records) <= MAX_PAGE_RECORDS
            or any(type(record) is not dict for record in records)):
        raise InvalidArtifact("invalid prepared page append")
    packed = _encode(records)
    with _stage_work(stage, now) as (conn, manifest):
        existing = conn.execute(select(P).where(P.c.inventory_id == stage.inventory_id,
            P.c.kind == kind, P.c.page_index == page_index)).mappings().first()
        if existing is not None:
            if (existing["ordinal_start"] != ordinal_start or existing["payload_sha256"] != packed["payload_sha256"]
                    or _decode(existing) != records):
                raise InvalidArtifact("prepared page retry changed content")
            return _descriptor("page", existing)
        prior = conn.execute(select(P).where(P.c.inventory_id == stage.inventory_id,
            P.c.kind == kind).order_by(P.c.page_index.desc()).limit(1)).mappings().first()
        if page_index != (prior["page_index"] + 1 if prior else 0) or ordinal_start != (prior["ordinal_end"] if prior else 0):
            raise InvalidArtifact("prepared pages must be contiguous")
        ghosts = sum(record.get("is_ghost") == 1 for record in records) if kind == "impressions" else 0
        real_start, ghost_start = (prior["real_end"], prior["ghost_end"]) if prior else (0, 0)
        row = dict(inventory_id=stage.inventory_id, kind=kind, page_index=page_index,
            ordinal_start=ordinal_start, ordinal_end=ordinal_start + len(records), real_start=real_start,
            real_end=real_start + len(records) - ghosts, ghost_start=ghost_start, ghost_end=ghost_start + ghosts,
            **packed)
        _write(conn, P, [row])
        return _descriptor("page", row)


def put_nodes(stage, *, nodes, now=None):
    if type(nodes) is not list:
        raise InvalidArtifact("invalid diagnostic append")
    with _stage_work(stage, now) as (conn, manifest):
        for node in nodes:
            value = v1._db_row(db.deck_diagnostic_snapshots_table, node)
            if value["user_id"] != manifest["user_id"] or len(value["snapshot_id"]) != 64:
                raise InvalidArtifact("foreign prepared diagnostic node")
            v1._time(value["created_at"])
            packed = _encode(value)
            prior = conn.execute(select(N).where(N.c.inventory_id == stage.inventory_id,
                N.c.snapshot_id == value["snapshot_id"])).mappings().first()
            if prior is not None:
                if prior["payload_sha256"] != packed["payload_sha256"] or _decode(prior) != value:
                    raise InvalidArtifact("prepared diagnostic retry changed frozen representation")
                continue
            _write(conn, N, [dict(inventory_id=stage.inventory_id, snapshot_id=value["snapshot_id"], **packed)])


def finish_metadata(stage, *, metadata, now=None):
    if type(metadata) is not dict or type(metadata.get("codec")) is not dict:
        raise InvalidArtifact("invalid prepared metadata")
    if ATTESTATION_KEY in metadata:
        raise InvalidArtifact("caller supplied reserved prepared attestation")
    info = metadata["codec"]
    for key in ("card_count", "impression_count", "ghost_count"):
        if type(info.get(key)) is not int or info[key] < 0:
            raise InvalidArtifact("invalid prepared completion count")
    candidate = metadata.get("candidate_set")
    if candidate is not None:
        list(_sql_chunks([v1._db_row(db.deck_candidate_sets_table, candidate)]))
    packed, digest = _text_pair(metadata)
    with _stage_work(stage, now) as (conn, row):
        if row["metadata_json"] is not None:
            if row["metadata_sha256"] != digest:
                raise InvalidArtifact("prepared metadata retry changed content")
            return
        _update(conn, update(M).where(M.c.inventory_id == stage.inventory_id),
            {"metadata_json": packed, "metadata_sha256": digest,
             **{key: info[key] for key in ("card_count", "impression_count", "ghost_count")}})


def _seal_tree(conn, inventory_id, *, write_proofs=True):
    # Hash-only identity index: O(nodes/pages), not O(decoded private graphs).
    leaves = []
    for table, kind, order in ((P, "page", (P.c.kind, P.c.page_index)), (N, "node", (N.c.snapshot_id,))):
        columns = [col for col in table.c if col.name not in {"payload_json", "proof_json"}]
        for row in conn.execute(select(*columns).where(table.c.inventory_id == inventory_id).order_by(*order)).mappings():
            key = {name: row[name] for name in (("kind", "page_index") if kind == "page" else ("snapshot_id",))}
            leaves.append((table, key, _leaf(kind, row)))
    if not leaves:
        return _hash("empty prepared tree"), 0, 0
    levels = [[item[2] for item in leaves]]
    while len(levels[-1]) > 1:
        current = levels[-1]
        levels.append([_pair(current[i], current[min(i + 1, len(current) - 1)]) for i in range(0, len(current), 2)])
    def updates(table):
        for index, (owner, key, _) in enumerate(leaves):
            if owner is not table:
                continue
            proof, cursor = [], index
            for level in levels[:-1]:
                sibling = cursor - 1 if cursor % 2 else min(cursor + 1, len(level) - 1)
                proof.append([bool(cursor % 2), level[sibling]])
                cursor //= 2
            yield {"p_inventory": inventory_id, "p_proof": v1._encode(proof),
                   **{"p_" + name: value for name, value in key.items()}}
    if write_proofs:
        for table in (P, N):
            names = ("kind", "page_index") if table is P else ("snapshot_id",)
            stmt = update(table).where(table.c.inventory_id == bindparam("p_inventory"),
                *(table.c[name] == bindparam("p_" + name) for name in names)).values(proof_json=bindparam("p_proof"))
            for chunk in _sql_chunks(updates(table)):
                conn.execute(stmt, chunk)
    return levels[-1][0], sum(item[0] is P for item in leaves), sum(item[0] is N for item in leaves)


def seal_inventory(stage, *, completion, dependency_receipt, model_identity, now=None):
    from . import prepared_trade_payload_v2 as codec
    with _stage_work(stage, now) as (conn, current):
        data = _header(current)
        metadata = _parse(_unpack(current["metadata_json"], current["metadata_sha256"]))
        original_header_sha, original_metadata_sha = current["header_sha256"], current["metadata_sha256"]
        if (v1.dependency_hash(data["dependency_receipt"]) != v1.dependency_hash(dependency_receipt)
                or v1.dependency_hash(data["model_identity"]) != v1.dependency_hash(model_identity)):
            raise StaleWork("prepared source/model changed before seal")
        if type(completion) is not dict or not completion or any(
                v1.dependency_hash(metadata.get(key)) != v1.dependency_hash(value) for key, value in completion.items()):
            raise InvalidArtifact("prepared completion differs from metadata")
        tree, pages, nodes = _seal_tree(conn, stage.inventory_id)
        pinned = dict(tree_sha256=tree, page_count=pages, node_count=nodes)
        pinned["root_sha256"] = _manifest_root({**current, **pinned})
        _update(conn, update(M).where(M.c.inventory_id == stage.inventory_id),
                {**pinned, "state": "validating"})
        stage.validation_root = pinned["root_sha256"]
    reader = stage.reader()
    validated = codec.restore_inventory(reader, user_id=data["scope"]["user_id"],
        league_id=data["scope"]["league_id"], now=None)
    info = metadata["codec"]
    if info["card_count"] != validated.card_count:
        raise InvalidArtifact("prepared completion card count mismatch")
    with _stage_work(stage, now, allowed=("validating",)) as (conn, current):
        actual = {}
        for kind in KINDS:
            actual[kind] = conn.execute(select(P.c.ordinal_end, P.c.real_end, P.c.ghost_end).where(
                P.c.inventory_id == stage.inventory_id, P.c.kind == kind).order_by(P.c.page_index.desc())
                .limit(1)).first() or (0, 0, 0)
        if (actual["cards"][0] != info["card_count"] or actual["impressions"][0] != info["impression_count"]
                or actual["admission"][0] != info["card_count"]
                or actual["impressions"][1] != info["card_count"] or actual["impressions"][2] != info["ghost_count"]):
            raise InvalidArtifact("prepared completion evidence count mismatch")
        tree, pages, nodes = _seal_tree(conn, stage.inventory_id, write_proofs=False)
        if (tree != pinned["tree_sha256"] or pages != pinned["page_count"] or nodes != pinned["node_count"]
                or current["root_sha256"] != stage.validation_root
                or current["header_sha256"] != original_header_sha
                or current["metadata_sha256"] != original_metadata_sha
                or _parse(_unpack(current["metadata_json"], current["metadata_sha256"])) != metadata):
            raise InvalidArtifact("prepared content changed during semantic validation")
        attested_metadata = {**metadata, ATTESTATION_KEY: _attestation(current, current["metadata_sha256"])}
        packed, digest = _text_pair(attested_metadata)
        values = dict(state="sealed", active_scope_key=current["scope_key"],
                      metadata_json=packed, metadata_sha256=digest)
        values["root_sha256"] = _manifest_root({**current, **values})
        conn.execute(update(M).where(M.c.active_scope_key == current["scope_key"]).values(
            active_scope_key=None, state="retired", adoption_token=None, adoption_lease_until=None))
        _update(conn, update(M).where(M.c.inventory_id == stage.inventory_id), values)
        v1._complete(conn, stage.claim, "ready" if info["card_count"] else "empty", v1._iso(now),
                     inventory_id=stage.inventory_id)
    return stage.inventory_id


def peek_inventory(scope, *, now=None):
    scope = v1._scope(scope)
    with db.engine.connect() as conn:
        row = conn.execute(select(M).where(M.c.active_scope_key == scope.key, M.c.state == "sealed",
            M.c.expires_at > v1._iso(now))).mappings().first()
        if row is None:
            return None
        try:
            if not _index_matches(conn, _header(row)):
                return None
        except (InvalidArtifact, KeyError, TypeError, ValueError):
            return None
    reader = Reader(row["inventory_id"], root=row["root_sha256"])
    from . import prepared_trade_payload_v2 as codec
    try:
        reader.verified_attestation(codec_version=codec.VERSION, validator_version=codec.VALIDATOR_VERSION)
    except (InvalidArtifact, KeyError, TypeError, ValueError):
        return None
    return reader


def load_inventory(scope, *, dependency_receipt, model_identity, now=None):
    reader = peek_inventory(scope, now=now)
    if reader:
        header = reader.header
        if (v1.dependency_hash(header["dependency_receipt"]) == v1.dependency_hash(dependency_receipt)
                and v1.dependency_hash(header["model_identity"]) == v1.dependency_hash(model_identity)):
            return reader
    return None


def claim_adoption(inventory_id, *, dependency_receipt, model_identity, publication, now=None, lease_seconds=120):
    if type(publication) is not dict or type(lease_seconds) is not int or not 1 <= lease_seconds <= 3600:
        raise InvalidArtifact("invalid adoption publication/lease")
    encoded, digest = _text_pair(publication)
    started, stamp, token = user_data_lifecycle.snapshot(), v1._iso(now), uuid.uuid4().hex
    try:
        header = Reader(inventory_id).header
        from . import prepared_trade_payload_v2 as codec
        Reader(inventory_id, root=header["root_sha256"]).verified_attestation(
            codec_version=codec.VERSION, validator_version=codec.VALIDATOR_VERSION)
    except (StaleWork, InvalidArtifact):
        return None
    if (header["expires_at"] <= stamp or v1.dependency_hash(header["dependency_receipt"]) != v1.dependency_hash(dependency_receipt)
            or v1.dependency_hash(header["model_identity"]) != v1.dependency_hash(model_identity)):
        return None
    list(_sql_chunks([{str(i): uid for i, uid in enumerate(header["participants"])}]))
    with v1._work(header["participants"], started), db.engine.begin() as conn:
        identities = v1._identity_receipt(conn, header["participants"], header["scope"]["user_id"])
        if not _index_matches(conn, header) or v1.dependency_hash(identities) != v1.dependency_hash(header["identity_receipt"]):
            raise StaleWork("prepared participant lifetime changed")
        changed = conn.execute(update(M).where(M.c.inventory_id == inventory_id, M.c.state == "sealed",
            M.c.root_sha256 == header["root_sha256"], M.c.active_scope_key.is_not(None), M.c.expires_at > stamp,
            or_(M.c.adoption_token.is_(None), M.c.adoption_lease_until <= stamp)).values(
                adoption_token=token, adoption_lease_until=v1._iso(v1._time(now) + timedelta(seconds=lease_seconds))))
        if changed.rowcount != 1:
            return None
        current = conn.execute(select(M).where(M.c.inventory_id == inventory_id)).mappings().one()
        if current["adoption_json"] is None:
            _update(conn, update(M).where(M.c.inventory_id == inventory_id),
                    {"adoption_json": encoded, "adoption_sha256": digest})
        else:
            publication = _parse(_unpack(current["adoption_json"], current["adoption_sha256"]))
        return {"inventory_id": inventory_id, "token": token, "root_sha256": header["root_sha256"],
            "publication": publication, "published_count": current["adoption_prefix"],
            "ghost_published_count": current["adoption_ghost_prefix"], "card_count": header["card_count"],
            "ghost_count": header["ghost_count"], "participants": header["participants"], "work_started": started}


@contextmanager
def _adoption_work(claim, now):
    list(_sql_chunks([{str(i): uid for i, uid in enumerate(claim["participants"])}]))
    with v1._work(claim["participants"], claim["work_started"]), db.engine.begin() as conn:
        # Identity rows precede manifest locks, matching deletion lock order.
        initial = conn.execute(select(M).where(M.c.inventory_id == claim["inventory_id"])).mappings().first()
        if initial is None:
            raise StaleWork("prepared inventory deleted")
        header = _header(initial)
        identities = v1._identity_receipt(conn, header["participants"], header["scope"]["user_id"])
        row = conn.execute(select(M).where(M.c.inventory_id == claim["inventory_id"], M.c.state == "sealed",
            M.c.active_scope_key.is_not(None), M.c.root_sha256 == claim["root_sha256"],
            M.c.adoption_token == claim["token"], M.c.adoption_lease_until > v1._iso(now),
            M.c.expires_at > v1._iso(now)).with_for_update()).mappings().first()
        if row is None:
            raise StaleWork("adoption lease expired or inventory replaced")
        header = _header(row)
        if (header["participants"] != claim["participants"] or not _index_matches(conn, header)
                or any(type(claim.get(key)) is not int or claim[key] != header[key]
                       for key in ("card_count", "ghost_count"))
                or v1.dependency_hash(identities) != v1.dependency_hash(header["identity_receipt"])):
            raise StaleWork("prepared participant lifetime changed")
        if v1.dependency_hash(header["publication"]) != v1.dependency_hash(claim["publication"]):
            raise StaleWork("prepared publication changed")
        if v1._time(row["adoption_lease_until"]) - v1._time(now) < timedelta(seconds=60):
            until = v1._iso(min(v1._time(now) + timedelta(seconds=120), v1._time(row["expires_at"])))
            conn.execute(update(M).where(M.c.inventory_id == claim["inventory_id"],
                M.c.adoption_token == claim["token"]).values(adoption_lease_until=until))
        yield conn, row, header


def _projection(reader, card_start, card_end, ghost_start, ghost_end):
    from .prepared_trade_payload_v2 import (DiagnosticResolver, _json, _size, MAX_BATCH_BYTES,
                                            validate_admission_binding)
    header, metadata = reader.header, reader.metadata()
    cards = reader.read_cards(card_start, card_end)
    real_rows = reader.read_impressions(card_start, card_end)
    entries = reader.read_admission(card_start, card_end)
    for index, (entry, record, original) in enumerate(zip(entries, cards, real_rows)):
        validate_admission_binding(entry, record, original, ordinal=card_start + index)
    impressions = real_rows + reader.read_impressions(ghost_start, ghost_end, ghosts=True)
    resolver = DiagnosticResolver(reader, user_id=header["scope"]["user_id"], job_id=metadata["codec"]["job_id"])
    features = [_json(item["features_json"]) for item in impressions]
    snapshots = resolver.closure(features)
    _size({"cards": cards, "impressions": impressions, "snapshots": snapshots}, MAX_BATCH_BYTES)
    bundle = {"cards": cards, "impressions": impressions, "snapshots": snapshots,
              "candidate_set": metadata.get("candidate_set"), "job_id": metadata["codec"]["job_id"]}
    first = card_start == 0 and (card_end > 0 or header["card_count"] == 0 and ghost_start == 0)
    mutations = [item for item in metadata.get("mutations", [])
                 if first or item.get("kind") != "resuppress"]
    return {"scope": header["scope"], "payload": {"inventory": bundle, "mutations": mutations}}


def _ensure_exact(conn, table, key, rows):
    total = 0
    for chunk in _sql_chunks(v1._db_row(table, row) for row in rows):
        total += v1._ensure_exact_rows(conn, table, key, chunk)
    return total


def ensure_adoption_evidence(claim, *, candidate_set, rows, ordinal_start, ordinal_end,
                             ghost_start=0, ghost_end=0, now=None):
    reader = Reader(claim["inventory_id"], root=claim["root_sha256"])
    data = _projection(reader, ordinal_start, ordinal_end, ghost_start, ghost_end)
    expected_ids = [row["impression_id"] for row in data["payload"]["inventory"]["impressions"]]
    if type(rows) is not list or [row.get("impression_id") for row in rows] != expected_ids:
        raise InvalidArtifact("publication differs from exact prepared range")
    bound, expected_candidate, snapshots = v1._adoption_rows(data, claim["publication"],
        claim["inventory_id"], candidate_set, rows)
    with _adoption_work(claim, now) as (conn, current, header):
        if ordinal_start > current["adoption_prefix"] or ghost_start > current["adoption_ghost_prefix"]:
            raise InvalidArtifact("publication skips an uncommitted prepared range")
        counts = {"candidate_sets": 0, "snapshots": 0, "impressions": 0}
        if candidate_set is not None:
            counts["candidate_sets"] = _ensure_exact(conn, db.deck_candidate_sets_table, "candidate_set_id", [candidate_set])
        if expected_candidate is not None:
            existing = conn.execute(select(db.deck_candidate_sets_table).where(
                db.deck_candidate_sets_table.c.candidate_set_id == expected_candidate["candidate_set_id"])).mappings().first()
            if existing is None or v1.dependency_hash({str(k): v for k, v in existing.items()}) != v1.dependency_hash(v1._db_row(db.deck_candidate_sets_table, expected_candidate)):
                raise InvalidArtifact("candidate dependency not durably available")
        counts["snapshots"] = _ensure_exact(conn, db.deck_diagnostic_snapshots_table, "snapshot_id", snapshots)
        counts["impressions"] = _ensure_exact(conn, db.deck_impressions_table, "impression_id", bound)
        v1._apply_mutations(conn, data, claim["publication"], bound)
        return counts


def checkpoint_adoption(claim, *, published_count, expected_prefix, ghost_published_count=0,
                        expected_ghost_prefix=0, now=None, complete=False):
    values = (published_count, expected_prefix, ghost_published_count, expected_ghost_prefix)
    if (any(type(value) is not int for value in values) or type(complete) is not bool
            or not 0 <= expected_prefix <= published_count <= claim["card_count"]
            or not 0 <= expected_ghost_prefix <= ghost_published_count <= claim["ghost_count"]
            or published_count - expected_prefix > MAX_PAGE_RECORDS
            or ghost_published_count - expected_ghost_prefix > MAX_PAGE_RECORDS
            or (complete and (published_count != claim["card_count"] or ghost_published_count != claim["ghost_count"]))):
        raise InvalidArtifact("invalid prepared publication cursor")
    reader = Reader(claim["inventory_id"], root=claim["root_sha256"])
    # These immutable, Merkle-authenticated originals establish only the new
    # suffix's durable IDs. Evidence binding already happened atomically in
    # ensure_adoption_evidence; do not re-expand every diagnostic a second time.
    metadata = reader.metadata()
    originals = reader.read_impressions(expected_prefix, published_count) + reader.read_impressions(
        expected_ghost_prefix, ghost_published_count, ghosts=True)
    with _adoption_work(claim, now) as (conn, current, header):
        if current["adoption_prefix"] != expected_prefix or current["adoption_ghost_prefix"] != expected_ghost_prefix:
            raise StaleWork("prepared durable prefix changed")
        table = db.deck_impressions_table
        if originals:
            actual = set(conn.execute(select(table.c.impression_id).where(
                table.c.impression_id.in_([row["impression_id"] for row in originals]),
                table.c.user_id == header["scope"]["user_id"], table.c.league_id == header["scope"]["league_id"],
                table.c.deck_job_id == metadata["codec"]["job_id"])).scalars())
            if actual != {row["impression_id"] for row in originals}:
                raise InvalidArtifact("checkpoint would expose non-durable evidence")
        candidate = metadata["candidate_set"]
        if candidate is not None:
            actual = conn.execute(select(db.deck_candidate_sets_table).where(
                db.deck_candidate_sets_table.c.candidate_set_id == candidate["candidate_set_id"])).mappings().first()
            if actual is None or v1.dependency_hash({str(k): v for k, v in actual.items()}) != v1.dependency_hash(v1._db_row(db.deck_candidate_sets_table, candidate)):
                raise InvalidArtifact("checkpoint candidate evidence missing or changed")
        changed = conn.execute(update(M).where(M.c.inventory_id == claim["inventory_id"],
            M.c.adoption_token == claim["token"], M.c.adoption_prefix == expected_prefix,
            M.c.adoption_ghost_prefix == expected_ghost_prefix).values(adoption_prefix=published_count,
                adoption_ghost_prefix=ghost_published_count,
                **({"adoption_token": None, "adoption_lease_until": None} if complete else {})))
        if changed.rowcount != 1:
            raise StaleWork("prepared durable prefix changed")


def release_adoption(claim):
    with db.engine.begin() as conn:
        return bool(conn.execute(update(M).where(M.c.inventory_id == claim["inventory_id"],
            M.c.adoption_token == claim["token"]).values(adoption_token=None, adoption_lease_until=None)).rowcount)


def _drop(conn, ids):
    total = 0
    for inventory_id in ids:
        for table in (P, N):
            conn.execute(delete(table).where(table.c.inventory_id == inventory_id))
        conn.execute(delete(db.prepared_trade_participants_table).where(
            db.prepared_trade_participants_table.c.subject_kind == SUBJECT_KIND,
            db.prepared_trade_participants_table.c.subject_id == inventory_id))
        total += conn.execute(delete(M).where(M.c.inventory_id == inventory_id)).rowcount
    return total


def abort_inventory(stage, *, now=None):
    with _stage_work(stage, now, allowed=("staging", "validating")) as (conn, row):
        return _drop(conn, [stage.inventory_id])


def invalidate_inventory(scope):
    scope = v1._scope(scope)
    with db.engine.begin() as conn:
        ids = conn.execute(select(M.c.inventory_id).where(M.c.scope_key == scope.key)).scalars().all()
        return _drop(conn, ids)


def retire_invalid_inventory(inventory_id, root_sha256):
    """Quarantine only the proven-invalid active root, preserving all history.

    The caller must distinguish stored integrity failures from transient SQL
    outages and stale work. No private content is decoded here: the failed
    header/page itself may be corrupt. A replacement or already-retired root
    cannot be changed by this conditional update.
    """
    if (type(inventory_id) is not str or not 0 < len(inventory_id) <= 128
            or type(root_sha256) is not str or len(root_sha256) != 64
            or any(char not in "0123456789abcdef" for char in root_sha256)):
        raise InvalidArtifact("invalid prepared retirement binding")
    with db.engine.begin() as conn:
        changed = conn.execute(update(M).where(M.c.inventory_id == inventory_id,
            M.c.root_sha256 == root_sha256, M.c.state == "sealed",
            M.c.active_scope_key.is_not(None)).values(state="retired", active_scope_key=None,
                adoption_token=None, adoption_lease_until=None))
        return changed.rowcount == 1


def prune(*, now=None):
    total = 0
    while True:
        with db.engine.begin() as conn:
            targets = db.prepared_trade_targets_table
            live_generation = select(targets.c.target_id).where(targets.c.target_id == M.c.target_id,
                targets.c.status == "running", targets.c.lease_token == M.c.generation_token,
                targets.c.lease_until > v1._iso(now)).exists()
            ids = conn.execute(select(M.c.inventory_id).where(or_(M.c.expires_at <= v1._iso(now),
                M.c.state == "retired", M.c.state.in_(("staging", "validating")) & ~live_generation))
                .order_by(M.c.inventory_id).limit(20)).scalars().all()
            if not ids:
                return total
            total += _drop(conn, ids)


def delete_for_users(conn, user_ids):
    index = db.prepared_trade_participants_table
    predicate = or_(M.c.user_id.in_(user_ids), M.c.inventory_id.in_(select(index.c.subject_id).where(
        index.c.subject_kind == SUBJECT_KIND, index.c.participant_user_id.in_(user_ids))))
    total = 0
    while True:
        ids = conn.execute(select(M.c.inventory_id).where(predicate).limit(20)).scalars().all()
        if not ids:
            return total
        total += _drop(conn, ids)
