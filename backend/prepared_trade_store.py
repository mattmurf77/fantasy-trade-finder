"""Private durable prepared offers and bounded, resumable work leases.

This module neither generates offers nor writes impression/activity rows. A
matching hash is an integrity/binding check, NOT a certificate of source
freshness: callers must refresh and compare all consumed inputs. All database
access resolves database.engine at call time. No server imports, pickle, or
implicit user creation. Times are timezone-aware UTC and reads never renew TTL.
"""
from contextlib import ExitStack, contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import base64
import binascii
import hashlib
import json
import math
import re
import uuid
import zlib

from sqlalchemy import Float, Integer, delete, func, insert, or_, select, update

from . import database as db, user_data_lifecycle

SCHEMA_VERSION = 1
MAX_PAYLOAD_BYTES = 64 * 1024 * 1024  # Resource protection, never an offer cap.
MAX_STORED_PAYLOAD_BYTES = 2 * 1024 * 1024  # One artifact SQL value, incl encoding.
STORAGE_PREFIX = "prepared-zlib-base64-1:"
MAX_RETENTION = timedelta(hours=24)
INSERT_CHUNK = 200
TERMINAL_STATUSES = frozenset({
    "ready", "empty", "reused", "deferred", "unsupported", "source_error",
    "stale", "error", "cancelled",
})


class InvalidArtifact(ValueError):
    """Unsupported, corrupt, inconsistent, or oversized prepared artifact."""


class StaleWork(RuntimeError):
    """The original claim, account lifetime, or inventory is no longer current."""


@dataclass(frozen=True)
class InventoryScope:
    user_id: str
    league_id: str
    league_user_id: str
    scoring_format: str
    request_key: str

    def __post_init__(self):
        for value in asdict(self).values():
            if type(value) is not str or not value or len(value) > 1024:
                raise InvalidArtifact("scope fields must be nonempty bounded strings")

    def as_dict(self) -> dict:
        return asdict(self)

    @property
    def key(self) -> str:
        return dependency_hash(self.as_dict())


def _strict(value, depth=0):
    if depth > 100:
        raise InvalidArtifact("JSON nesting exceeds safety bound")
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise InvalidArtifact("nonfinite JSON number")
        return
    if type(value) is list:
        for item in value:
            _strict(item, depth + 1)
        return
    if type(value) is dict and all(type(k) is str for k in value):
        for item in value.values():
            _strict(item, depth + 1)
        return
    raise InvalidArtifact("only plain JSON types and string keys are supported")


def _encode(value) -> str:
    _strict(value)
    result = json.dumps(value, sort_keys=True, separators=(",", ":"),
                        ensure_ascii=False, allow_nan=False)
    if len(result.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise InvalidArtifact("prepared payload exceeds byte limit; nothing truncated")
    return result


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidArtifact("duplicate JSON object key")
        result[key] = value
    return result


def _decode(value: str):
    if type(value) is not str or len(value.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise InvalidArtifact("invalid JSON payload size")
    try:
        result = json.loads(value, object_pairs_hook=_pairs,
                            parse_constant=lambda _: (_ for _ in ()).throw(
                                InvalidArtifact("nonfinite JSON number")))
        _strict(result)
        return result
    except (ValueError, TypeError, RecursionError) as exc:
        raise InvalidArtifact("invalid prepared JSON") from exc


def dependency_hash(value) -> str:
    """Canonical strict JSON hash; array order and numeric types are retained."""
    return hashlib.sha256(_encode(value).encode("utf-8")).hexdigest()


def _pack_payload(raw: str) -> str:
    """Fixed safe transport codec; logical JSON/checksum/schema stay unchanged."""
    encoded = raw.encode("utf-8")
    if len(encoded) > MAX_PAYLOAD_BYTES:
        raise InvalidArtifact("prepared logical payload exceeds byte limit")
    result = STORAGE_PREFIX + base64.b64encode(zlib.compress(encoded, level=6)).decode("ascii")
    if len(result) > MAX_STORED_PAYLOAD_BYTES:
        raise InvalidArtifact("prepared encoded payload exceeds SQL byte limit; nothing truncated")
    return result


def _unpack_payload(stored: str) -> str:
    """Bound output while decompressing, rejecting trailing/partial streams.

    Small pre-codec plain JSON is supported; no legacy record bypasses the
    encoded transport limit. A future codec must use a new explicit prefix.
    """
    if type(stored) is not str or len(stored.encode("utf-8")) > MAX_STORED_PAYLOAD_BYTES:
        raise InvalidArtifact("prepared stored payload exceeds SQL byte limit")
    if not stored.startswith(STORAGE_PREFIX):
        if not stored.startswith("{"):
            raise InvalidArtifact("unsupported prepared storage codec")
        if len(stored.encode("utf-8")) > MAX_PAYLOAD_BYTES:
            raise InvalidArtifact("prepared logical payload exceeds byte limit")
        return stored
    try:
        compressed = base64.b64decode(stored[len(STORAGE_PREFIX):], validate=True)
        inflater = zlib.decompressobj()
        raw = inflater.decompress(compressed, MAX_PAYLOAD_BYTES + 1)
        if (len(raw) > MAX_PAYLOAD_BYTES or not inflater.eof or inflater.unconsumed_tail
                or inflater.unused_data):
            raise InvalidArtifact("oversized, truncated or trailing prepared compression stream")
        return raw.decode("utf-8")
    except (binascii.Error, zlib.error, UnicodeError, ValueError) as exc:
        raise InvalidArtifact("invalid prepared compression stream") from exc


def _artifact_text(row) -> str:
    raw = _unpack_payload(row["payload_json"])
    if hashlib.sha256(raw.encode("utf-8")).hexdigest() != row["payload_sha256"]:
        raise InvalidArtifact("prepared logical payload checksum mismatch")
    return raw


def _time(value=None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if type(value) is str:
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise InvalidArtifact("invalid timestamp") from exc
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise InvalidArtifact("timezone-aware timestamp required")
    return value.astimezone(timezone.utc)


def _iso(value=None) -> str:
    return _time(value).isoformat(timespec="microseconds")


def _scope(value) -> InventoryScope:
    if isinstance(value, InventoryScope):
        return value
    if type(value) is not dict:
        raise InvalidArtifact("invalid inventory scope")
    try:
        return InventoryScope(**value)
    except TypeError as exc:
        raise InvalidArtifact("invalid inventory scope") from exc


def _participants(scope, values):
    if type(values) is not list or any(type(v) is not str or not v for v in values):
        raise InvalidArtifact("participants must be nonempty identity strings")
    return sorted(set(values) | {scope.user_id, scope.league_user_id})


@contextmanager
def _work(participants, started):
    if type(started) is not int:
        raise InvalidArtifact("original lifecycle snapshot required")
    with ExitStack() as stack:
        for uid in sorted(set(participants)):
            if not stack.enter_context(user_data_lifecycle.capture(uid, started=started).active()):
                raise StaleWork("account work was revoked")
        yield


def _identity_receipt(conn, participants, owner):
    """Lock existing app identities in deletion order; imported peers may lack rows."""
    from .accounts import ACCOUNT_USER_PREFIX, is_account_user_id
    users = conn.execute(select(db.users_table.c.sleeper_user_id,
                                db.users_table.c.created_at).where(
        db.users_table.c.sleeper_user_id.in_(participants)).order_by(
        db.users_table.c.sleeper_user_id).with_for_update()).all()
    account_ids = sorted(uid[len(ACCOUNT_USER_PREFIX):] for uid in participants
                         if is_account_user_id(uid))
    accounts = conn.execute(select(db.accounts_table.c.account_id,
                                   db.accounts_table.c.created_at,
                                   db.accounts_table.c.sleeper_user_id).where(
        db.accounts_table.c.account_id.in_(account_ids)).order_by(
        db.accounts_table.c.account_id).with_for_update()).all()
    if owner not in {r[0] for r in users} and not (
            is_account_user_id(owner) and owner[len(ACCOUNT_USER_PREFIX):] in {r[0] for r in accounts}):
        raise StaleWork("owning app identity no longer exists")
    return {"users": [list(row) for row in users], "accounts": [list(row) for row in accounts]}


def _index(conn, kind, subject_id, owner, participants):
    rows = [{"subject_kind": kind, "subject_id": subject_id, "user_id": owner,
             "participant_user_id": uid} for uid in participants]
    for start in range(0, len(rows), INSERT_CHUNK):
        conn.execute(insert(db.prepared_trade_participants_table), rows[start:start + INSERT_CHUNK])


def _drop_subjects(conn, kind, subject_ids):
    ids = list(subject_ids)
    table = (db.prepared_trade_inventories_table if kind == "inventory"
             else db.prepared_trade_targets_table)
    column = table.c.inventory_id if kind == "inventory" else table.c.target_id
    count = 0
    for start in range(0, len(ids), INSERT_CHUNK):
        chunk = ids[start:start + INSERT_CHUNK]
        conn.execute(delete(db.prepared_trade_participants_table).where(
            db.prepared_trade_participants_table.c.subject_kind == kind,
            db.prepared_trade_participants_table.c.subject_id.in_(chunk)))
        count += conn.execute(delete(table).where(column.in_(chunk))).rowcount
    return count


def _insert_absent(conn, table, values, key):
    # Use one real DML transaction, not an outermost SQLite SAVEPOINT (whose
    # RELEASE can commit independently under legacy sqlite transaction mode).
    if conn.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as upsert
    else:
        from sqlalchemy.dialects.sqlite import insert as upsert
    return conn.execute(upsert(table).values(**values).on_conflict_do_nothing(index_elements=[key])).rowcount


def create_sweep(idempotency_key: str, targets: list[dict], *, started: int,
                 now=None, max_attempts: int = 3, coverage: dict | None = None) -> str:
    """Freeze scope/binding/participants once. Repeat key must have identical input.

    Capture `started = user_data_lifecycle.snapshot()` BEFORE cohort/source reads.
    Target shape: {scope: InventoryScope.as_dict(), participants: [IDs], binding: {}}.
    Every consumed participant must be known here, before generation begins.
    """
    if type(idempotency_key) is not str or not idempotency_key or len(idempotency_key) > 512:
        raise InvalidArtifact("invalid sweep idempotency key")
    if type(max_attempts) is not int or not 1 <= max_attempts <= 10:
        raise InvalidArtifact("invalid retry bound")
    coverage = {} if coverage is None else coverage
    def aggregate(value):
        if type(value) is bool:  # e.g. discovery_complete, never a user attribute.
            return
        if type(value) is int and value >= 0:
            return
        if type(value) is dict and all(type(key) is str and re.fullmatch(r"[a-z0-9_]{1,80}", key) for key in value):
            for child in value.values():
                aggregate(child)
            return
        raise InvalidArtifact("coverage must contain non-identifying aggregate counts/flags")
    aggregate(coverage)
    coverage_json = _encode(coverage)
    normalized, keys = [], set()
    for value in targets:
        if type(value) is not dict or set(value) != {"scope", "participants", "binding"}:
            raise InvalidArtifact("invalid target shape")
        scope = _scope(value["scope"])
        if scope.key in keys:
            raise InvalidArtifact("duplicate target scope")
        keys.add(scope.key)
        normalized.append({"scope": scope.as_dict(), "participants": _participants(scope, value["participants"]),
                           "binding": value["binding"]})
    normalized.sort(key=lambda item: dependency_hash(item["scope"]))
    normalized = _decode(_encode(normalized))
    cohort_hash = dependency_hash({"targets": normalized, "max_attempts": max_attempts, "coverage": coverage})
    participants = {uid for item in normalized for uid in item["participants"]}
    sweeps, targets_table = db.prepared_trade_sweeps_table, db.prepared_trade_targets_table
    stamp, sweep_id = _iso(now), uuid.uuid4().hex
    with _work(participants, started), db.engine.begin() as conn:
        existing = conn.execute(select(sweeps).where(sweeps.c.idempotency_key == idempotency_key)).mappings().first()
        if existing:
            if existing["cohort_hash"] != cohort_hash:
                raise InvalidArtifact("idempotency key already binds a different cohort")
            return existing["sweep_id"]
        # Lock app rows once, in globally sorted order, before any target writes.
        if normalized:
            _identity_receipt(conn, sorted(participants), normalized[0]["scope"]["user_id"])
        inserted = _insert_absent(conn, sweeps, dict(sweep_id=sweep_id, idempotency_key=idempotency_key,
            cohort_hash=cohort_hash, coverage_json=coverage_json, created_at=stamp, updated_at=stamp,
            status="running" if normalized else "complete", target_count=len(normalized), deleted_count=0), "idempotency_key")
        if not inserted:
            existing = conn.execute(select(sweeps).where(sweeps.c.idempotency_key == idempotency_key)).mappings().one()
            if existing["cohort_hash"] != cohort_hash:
                raise InvalidArtifact("idempotency key already binds a different cohort")
            return existing["sweep_id"]
        for item in normalized:
            # Only this target's app identities belong in its lifetime receipt.
            item["identity_receipt"] = _identity_receipt(conn, item["participants"], item["scope"]["user_id"])
            target_id = uuid.uuid4().hex
            conn.execute(insert(targets_table).values(target_id=target_id, sweep_id=sweep_id,
                scope_key=dependency_hash(item["scope"]), user_id=item["scope"]["user_id"],
                payload_json=_encode(item), status="pending", attempts=0, max_attempts=max_attempts,
                available_at=stamp, updated_at=stamp))
            _index(conn, "target", target_id, item["scope"]["user_id"], item["participants"])
    return sweep_id


def _ensure_worker(conn):
    table = db.prepared_trade_worker_table
    if not conn.execute(select(table.c.worker_id).where(table.c.worker_id == 1)).first():
        _insert_absent(conn, table, {"worker_id": 1}, "worker_id")


def _release_worker(conn, token):
    table = db.prepared_trade_worker_table
    conn.execute(update(table).where(table.c.worker_id == 1, table.c.lease_token == token)
                 .values(lease_token=None, lease_until=None, target_id=None))


def _finish_sweep(conn, sweep_id, stamp):
    targets, sweeps = db.prepared_trade_targets_table, db.prepared_trade_sweeps_table
    pending = conn.execute(select(func.count()).select_from(targets).where(
        targets.c.sweep_id == sweep_id, targets.c.status.in_(("pending", "running")))).scalar_one()
    conn.execute(update(sweeps).where(sweeps.c.sweep_id == sweep_id, sweeps.c.status == "running")
                 .values(status="running" if pending else "complete", updated_at=stamp))


def claim_target(sweep_id: str, *, now=None, lease_seconds: int = 300) -> dict | None:
    """Atomically claim at most one target globally; expired claims are retryable.

    Returned private claim includes `scope`, `binding`, `participants`, and the
    original in-process `work_started` marker. Do not expose it on public status.
    Callers must freshly resolve/validate sources after every recovered claim.
    """
    if type(lease_seconds) is not int or not 1 <= lease_seconds <= 3600:
        raise InvalidArtifact("invalid lease duration")
    started, stamp = user_data_lifecycle.snapshot(), _iso(now)
    until = _iso(_time(now) + timedelta(seconds=lease_seconds))
    token = uuid.uuid4().hex
    workers, targets, sweeps = db.prepared_trade_worker_table, db.prepared_trade_targets_table, db.prepared_trade_sweeps_table
    with db.engine.begin() as conn:
        _ensure_worker(conn)
        acquired = conn.execute(update(workers).where(workers.c.worker_id == 1,
            or_(workers.c.lease_token.is_(None), workers.c.lease_until <= stamp))
            .values(lease_token=token, lease_until=until, target_id=None)).rowcount
        if acquired != 1:
            return None
        # A dead process must not strand its target after the singleton expires.
        conn.execute(update(targets).where(targets.c.status == "running", targets.c.lease_until <= stamp)
                     .values(status="pending", lease_token=None, lease_until=None, updated_at=stamp))
        conn.execute(update(targets).where(targets.c.status == "pending", targets.c.attempts >= targets.c.max_attempts)
                     .values(status="error", reason="retry_exhausted", updated_at=stamp))
        sweep = conn.execute(select(sweeps).where(sweeps.c.sweep_id == sweep_id)).mappings().first()
        if not sweep or sweep["status"] != "running":
            _release_worker(conn, token)
            return None
        row = conn.execute(select(targets).where(targets.c.sweep_id == sweep_id,
            targets.c.status == "pending", targets.c.available_at <= stamp)
            .order_by(targets.c.available_at, targets.c.target_id).limit(1)).mappings().first()
        if not row:
            _release_worker(conn, token)
            _finish_sweep(conn, sweep_id, stamp)
            return None
        conn.execute(update(targets).where(targets.c.target_id == row["target_id"])
                     .values(status="running", attempts=row["attempts"] + 1,
                             lease_token=token, lease_until=until, updated_at=stamp))
        conn.execute(update(workers).where(workers.c.worker_id == 1, workers.c.lease_token == token)
                     .values(target_id=row["target_id"]))
        data = _decode(row["payload_json"])
        return {**data, "target_id": row["target_id"], "sweep_id": sweep_id,
                "lease_token": token, "lease_until": until, "work_started": started}


def _claimed(conn, claim, stamp):
    targets, workers = db.prepared_trade_targets_table, db.prepared_trade_worker_table
    worker = conn.execute(select(workers.c.worker_id).where(workers.c.worker_id == 1,
        workers.c.target_id == claim["target_id"], workers.c.lease_token == claim["lease_token"],
        workers.c.lease_until > stamp).with_for_update()).first()
    row = conn.execute(select(targets).where(targets.c.target_id == claim["target_id"],
        targets.c.sweep_id == claim["sweep_id"], targets.c.status == "running",
        targets.c.lease_token == claim["lease_token"], targets.c.lease_until > stamp)
        .with_for_update()).mappings().first()
    if not row or not worker:
        raise StaleWork("expired, stopped, superseded, or deleted preparation claim")
    data = _decode(row["payload_json"])
    if any(dependency_hash(claim[key]) != dependency_hash(data[key])
           for key in ("scope", "participants", "binding", "identity_receipt")):
        raise StaleWork("claim binding changed")
    return row, data


def _complete(conn, claim, status, stamp, *, reason=None, inventory_id=None, retry_at=None):
    targets = db.prepared_trade_targets_table
    row, _ = _claimed(conn, claim, stamp)
    retry = retry_at is not None and row["attempts"] < row["max_attempts"]
    conn.execute(update(targets).where(targets.c.target_id == claim["target_id"])
        .values(status="pending" if retry else status, reason=reason, inventory_id=inventory_id,
                lease_token=None, lease_until=None, updated_at=stamp,
                available_at=_iso(retry_at) if retry else stamp))
    _release_worker(conn, claim["lease_token"])
    _finish_sweep(conn, claim["sweep_id"], stamp)


def complete_target(claim: dict, *, status: str, reason: str | None = None,
                    retry_at=None, now=None) -> None:
    """Finish/explicitly retry without artifact; reason is a non-identifying code."""
    if status not in TERMINAL_STATUSES - {"ready", "empty"}:
        raise InvalidArtifact("invalid completion status")
    if reason is not None and (type(reason) is not str or not re.fullmatch(r"[a-z0-9_]{1,80}", reason)):
        raise InvalidArtifact("reason must be a bounded machine code, never exception/user text")
    with _work(claim["participants"], claim["work_started"]), db.engine.begin() as conn:
        inventory_id = None
        if status == "reused":
            table = db.prepared_trade_inventories_table
            inventory_id = conn.execute(select(table.c.inventory_id).where(
                table.c.scope_key == _scope(claim["scope"]).key, table.c.expires_at > _iso(now))).scalar_one_or_none()
            if inventory_id is None:
                raise StaleWork("reused inventory disappeared or expired")
        _complete(conn, claim, status, _iso(now), reason=reason, retry_at=retry_at, inventory_id=inventory_id)


def _card_count(payload):
    if type(payload) is dict and "inventory" in payload and "cards" not in payload:
        payload = payload["inventory"]
    if type(payload) is not dict or type(payload.get("cards")) is not list:
        raise InvalidArtifact("payload must contain ordered cards list")
    return len(payload["cards"])


def save_inventory(claim: dict, *, payload: dict, dependency_receipt: dict,
                   model_identity: dict, participants: list[str], created_at,
                   expires_at, now=None) -> str:
    """Atomic artifact replacement AND ready/empty claim completion.

    A claim token, original account lifetime, current identity receipt, and
    unexpired global lease must all match. SQL failure preserves the prior
    inventory and running claim. Never creates shown rows or account records.
    """
    scope = _scope(claim["scope"])
    participants = _participants(scope, participants)
    if participants != claim["participants"]:
        raise StaleWork("all consumed participants must be bound before generation")
    created, expiry, current = _time(created_at), _time(expires_at), _time(now)
    if created > current or not current < expiry <= created + MAX_RETENTION:
        raise InvalidArtifact("inventory expiry must be original, future, and at most 24 hours")
    if type(dependency_receipt) is not dict or type(model_identity) is not dict or not dependency_receipt or not model_identity:
        raise InvalidArtifact("explicit nonempty dependency/model receipts required")
    envelope = {"schema_version": SCHEMA_VERSION, "scope": scope.as_dict(),
                "created_at": _iso(created), "expires_at": _iso(expiry),
                "participants": participants, "dependency_receipt": dependency_receipt,
                "model_identity": model_identity, "identity_receipt": claim["identity_receipt"],
                "card_count": _card_count(payload), "payload": payload}
    encoded = _encode(envelope)  # Detached exact bytes before transactional writes.
    storage_json = _pack_payload(encoded)
    envelope = _decode(encoded)
    inventory_id, stamp = uuid.uuid4().hex, _iso(current)
    table = db.prepared_trade_inventories_table
    with _work(participants, claim["work_started"]), db.engine.begin() as conn:
        receipt = _identity_receipt(conn, participants, scope.user_id)
        _, data = _claimed(conn, claim, stamp)
        if dependency_hash(receipt) != dependency_hash(data["identity_receipt"]):
            raise StaleWork("app identity lifetime or account binding changed")
        old = conn.execute(select(table.c.inventory_id).where(table.c.scope_key == scope.key)).scalar_one_or_none()
        if old:
            _drop_subjects(conn, "inventory", [old])
        conn.execute(insert(table).values(inventory_id=inventory_id, scope_key=scope.key,
            user_id=scope.user_id, league_id=scope.league_id, schema_version=SCHEMA_VERSION,
            created_at=envelope["created_at"], expires_at=envelope["expires_at"],
            dependency_hash=dependency_hash(dependency_receipt), model_hash=dependency_hash(model_identity),
            card_count=envelope["card_count"], payload_sha256=hashlib.sha256(encoded.encode()).hexdigest(),
            payload_json=storage_json, adoption_prefix=0))
        _index(conn, "inventory", inventory_id, scope.user_id, participants)
        _complete(conn, claim, "ready" if envelope["card_count"] else "empty", stamp, inventory_id=inventory_id)
    return inventory_id


def _verified(row, scope, now):
    if not row or row["schema_version"] != SCHEMA_VERSION or row["expires_at"] <= _iso(now):
        return None
    try:
        raw = _artifact_text(row)
        data = _decode(raw)
        if set(data) != {"schema_version", "scope", "created_at", "expires_at", "participants",
                          "dependency_receipt", "model_identity", "identity_receipt", "card_count", "payload"}:
            return None
        if (type(data["schema_version"]) is not int or data["schema_version"] != SCHEMA_VERSION or _scope(data["scope"]) != scope
                or row["scope_key"] != scope.key or row["user_id"] != scope.user_id
                or row["league_id"] != scope.league_id or data["created_at"] != row["created_at"]
                or data["expires_at"] != row["expires_at"] or type(data["card_count"]) is not int
                or data["card_count"] != row["card_count"] or _card_count(data["payload"]) != row["card_count"]
                or dependency_hash(data["dependency_receipt"]) != row["dependency_hash"]
                or dependency_hash(data["model_identity"]) != row["model_hash"]
                or _participants(scope, data["participants"]) != data["participants"]
                or not _time(data["created_at"]) < _time(data["expires_at"]) <= _time(data["created_at"]) + MAX_RETENTION):
            return None
        publication = _decode(row["adoption_json"]) if row["adoption_json"] is not None else None
        if ((publication is not None and type(publication) is not dict)
                or (publication is not None and hashlib.sha256(row["adoption_json"].encode()).hexdigest() != row["adoption_sha256"])
                or (publication is None and row["adoption_sha256"] is not None)
                or type(row["adoption_prefix"]) is not int
                or not 0 <= row["adoption_prefix"] <= row["card_count"]):
            return None
        return {**data, "inventory_id": row["inventory_id"], "dependency_hash": row["dependency_hash"],
                "payload_sha256": row["payload_sha256"], "publication": publication,
                "published_count": row["adoption_prefix"]}
    except (InvalidArtifact, KeyError, TypeError, OverflowError):
        return None


def peek_inventory(scope: InventoryScope, *, now=None) -> dict | None:
    """Integrity-checked artifact including receipt; NO current-freshness claim.

    Caller must refresh sources and call load_inventory with the current receipt
    before adoption. This function does not extend TTL or issue an adoption lease.
    """
    scope = _scope(scope)
    with db.engine.connect() as conn:
        row = conn.execute(select(db.prepared_trade_inventories_table).where(
            db.prepared_trade_inventories_table.c.scope_key == scope.key)).mappings().first()
        result = _verified(row, scope, now)
        return result if result and _index_matches(conn, result) else None


def _index_matches(conn, artifact):
    table = db.prepared_trade_participants_table
    records = conn.execute(select(table.c.participant_user_id, table.c.user_id).where(
        table.c.subject_kind == "inventory", table.c.subject_id == artifact["inventory_id"])).all()
    return sorted(records) == [(uid, artifact["scope"]["user_id"]) for uid in artifact["participants"]]


def load_inventory(scope: InventoryScope, *, dependency_receipt: dict,
                   model_identity: dict, now=None) -> dict | None:
    """Return detached ordered payload only for exact receipts and original TTL."""
    result = peek_inventory(scope, now=now)
    if result and (result["dependency_hash"] == dependency_hash(dependency_receipt)
                   and dependency_hash(result["model_identity"]) == dependency_hash(model_identity)):
        return result
    return None


def claim_adoption(inventory_id: str, *, dependency_receipt: dict,
                   model_identity: dict, publication: dict, now=None,
                   lease_seconds: int = 120) -> dict | None:
    """Exclusive recoverable publication lease; returns original publication data.

    Caller first refreshes all sources. The publication mapping (e.g. serve time
    and job ID) is frozen on FIRST adoption and returned unchanged on recovery,
    allowing byte-identical evidence retries. No evidence is written here.
    `published_count` is the durable checkpoint, not a human view count.
    """
    if type(publication) is not dict or type(lease_seconds) is not int or not 1 <= lease_seconds <= 3600:
        raise InvalidArtifact("invalid adoption publication/lease")
    encoded = _encode(publication)
    stamp, started, token = _iso(now), user_data_lifecycle.snapshot(), uuid.uuid4().hex
    table = db.prepared_trade_inventories_table
    with db.engine.connect() as conn:
        row = conn.execute(select(table).where(table.c.inventory_id == inventory_id)).mappings().first()
    if not row:
        return None
    try:
        scope = _scope(_decode(_artifact_text(row))["scope"])
    except (InvalidArtifact, KeyError, TypeError):
        return None
    data = _verified(row, scope, now)
    if not data or data["dependency_hash"] != dependency_hash(dependency_receipt) or (
            dependency_hash(data["model_identity"]) != dependency_hash(model_identity)):
        return None
    with _work(data["participants"], started), db.engine.begin() as conn:
        if not _index_matches(conn, data):
            raise InvalidArtifact("incomplete participant deletion index")
        receipt = _identity_receipt(conn, data["participants"], scope.user_id)
        if dependency_hash(receipt) != dependency_hash(data["identity_receipt"]):
            raise StaleWork("app identity lifetime or account binding changed")
        changed = conn.execute(update(table).where(table.c.inventory_id == inventory_id,
            table.c.payload_sha256 == row["payload_sha256"], table.c.expires_at > stamp,
            or_(table.c.adoption_token.is_(None), table.c.adoption_lease_until <= stamp))
            .values(adoption_token=token, adoption_lease_until=_iso(_time(now) + timedelta(seconds=lease_seconds))))
        if changed.rowcount != 1:
            return None
        current = conn.execute(select(table).where(table.c.inventory_id == inventory_id)).mappings().one()
        if current["adoption_json"] is None:
            conn.execute(update(table).where(table.c.inventory_id == inventory_id)
                         .values(adoption_json=encoded, adoption_sha256=hashlib.sha256(encoded.encode()).hexdigest()))
        else:
            encoded = current["adoption_json"]
            if hashlib.sha256(encoded.encode()).hexdigest() != current["adoption_sha256"]:
                raise InvalidArtifact("corrupt original adoption metadata")
        return {"inventory_id": inventory_id, "token": token, "publication": _decode(encoded),
                "published_count": current["adoption_prefix"], "card_count": current["card_count"],
                "participants": data["participants"], "work_started": started,
                "payload_sha256": row["payload_sha256"]}


def checkpoint_adoption(claim: dict, *, published_count: int, expected_prefix: int,
                        now=None, complete: bool = False) -> None:
    """Advance only AFTER evidence commit. Retry the exact batch after a crash.

    The evidence writer is idempotent, so a crash between its commit and this
    checkpoint repeats evidence safely rather than falsely declaring durability.
    A completed lease is released; immutable publication data remains for reuse.
    """
    if (type(published_count) is not int or type(expected_prefix) is not int
            or not 0 <= expected_prefix <= published_count <= claim["card_count"]
            or type(complete) is not bool or (complete and published_count != claim["card_count"])):
        raise InvalidArtifact("invalid publication prefix")
    table, stamp = db.prepared_trade_inventories_table, _iso(now)
    with _work(claim["participants"], claim["work_started"]), db.engine.begin() as conn:
        row = conn.execute(select(table).where(table.c.inventory_id == claim["inventory_id"],
            table.c.payload_sha256 == claim["payload_sha256"], table.c.adoption_token == claim["token"],
            table.c.adoption_lease_until > stamp, table.c.expires_at > stamp).with_for_update()).mappings().first()
        if not row:
            raise StaleWork("adoption lease expired or inventory replaced")
        data = _decode(_artifact_text(row))
        bundle = data["payload"].get("inventory", data["payload"])
        if published_count:
            originals = [item for item in bundle.get("impressions", []) if item.get("is_ghost") != 1]
            if len(originals) != row["card_count"]:
                raise InvalidArtifact("complete original evidence required for checkpoint")
            for start in range(0, published_count, INSERT_CHUNK):
                page = originals[start:min(start + INSERT_CHUNK, published_count)]
                actual = set(conn.execute(select(db.deck_impressions_table.c.impression_id).where(
                    db.deck_impressions_table.c.impression_id.in_([item["impression_id"] for item in page]),
                    db.deck_impressions_table.c.user_id == data["scope"]["user_id"],
                    db.deck_impressions_table.c.league_id == data["scope"]["league_id"],
                    db.deck_impressions_table.c.deck_job_id == bundle["job_id"])).scalars())
                if actual != {item["impression_id"] for item in page}:
                    raise InvalidArtifact("checkpoint would expose non-durable evidence")
        changed = conn.execute(update(table).where(table.c.inventory_id == claim["inventory_id"],
            table.c.payload_sha256 == claim["payload_sha256"], table.c.adoption_token == claim["token"],
            table.c.adoption_lease_until > stamp, table.c.expires_at > stamp,
            table.c.adoption_prefix == expected_prefix).values(adoption_prefix=published_count,
                **({"adoption_token": None, "adoption_lease_until": None} if complete else {})))
        if changed.rowcount != 1:
            raise StaleWork("adoption lease or exact durable prefix changed")


def release_adoption(claim: dict) -> bool:
    """Release only this exact token; preserve frozen serve metadata/progress."""
    table = db.prepared_trade_inventories_table
    with db.engine.begin() as conn:
        return conn.execute(update(table).where(table.c.inventory_id == claim["inventory_id"],
            table.c.adoption_token == claim["token"]).values(
                adoption_token=None, adoption_lease_until=None)).rowcount == 1


def _db_row(table, value):
    """Normalize only the SQL column's documented numeric coercion."""
    if type(value) is not dict or not set(value) <= set(table.c.keys()):
        raise InvalidArtifact("unknown evidence column")
    result = {}
    for column in table.c:
        item = value.get(column.name)
        if item is not None and isinstance(column.type, Float):
            if type(item) not in (float, int) or not math.isfinite(item):
                raise InvalidArtifact("invalid evidence float")
            item = float(item)
        elif item is not None and isinstance(column.type, Integer):
            if type(item) is not int:
                raise InvalidArtifact("invalid evidence integer")
        elif item is not None and type(item) is not str:
            raise InvalidArtifact("invalid evidence text")
        if item is None and not column.nullable:
            raise InvalidArtifact("missing required evidence column")
        result[str(column.name)] = item
    return result


def _ensure_exact_rows(conn, table, key, records):
    """Insert missing IDs only; an existing ID with different content is an error."""
    normalized = [_db_row(table, value) for value in records]
    if len({value[key] for value in normalized}) != len(normalized):
        raise InvalidArtifact("duplicate evidence ID in publication batch")
    inserted = 0
    for start in range(0, len(normalized), db.DECK_IMPRESSION_INSERT_ROWS):
        page = normalized[start:start + db.DECK_IMPRESSION_INSERT_ROWS]
        existing = {row[key]: {str(k): v for k, v in row.items()} for row in conn.execute(select(table).where(
            table.c[key].in_([value[key] for value in page]))).mappings()}
        new = []
        for value in page:
            prior = existing.get(value[key])
            if prior is None:
                new.append(value)
            elif dependency_hash(prior) != dependency_hash(value):
                raise InvalidArtifact("existing evidence ID binds different content")
        if new:
            conn.execute(insert(table), new)
            inserted += len(new)
    return inserted


def _adoption_rows(data, publication, inventory_id, candidate_set, rows):
    """Bind publication to reserved prepared evidence, allowing serve fields only."""
    from .deck_diagnostics import DIAGNOSTIC_KEYS, REFERENCE_KEY, dumps, is_reference
    payload = data["payload"]
    bundle = payload.get("inventory", payload)
    if type(bundle) is not dict or type(bundle.get("impressions")) is not list:
        raise InvalidArtifact("prepared evidence bundle required")
    originals = {row["impression_id"]: row for row in bundle["impressions"]}
    if len(originals) != len(bundle["impressions"]):
        raise InvalidArtifact("duplicate prepared impression ID")
    snapshot_rows = bundle.get("snapshots", [])
    if type(snapshot_rows) is not list:
        raise InvalidArtifact("invalid prepared diagnostic snapshots")
    snapshots = {}
    for row in snapshot_rows:
        normalized = _db_row(db.deck_diagnostic_snapshots_table, row)
        if normalized["snapshot_id"] in snapshots:
            raise InvalidArtifact("duplicate prepared diagnostic snapshot")
        snapshots[normalized["snapshot_id"]] = normalized
    scope = data["scope"]
    job_id = bundle.get("job_id")
    expanded, used = {}, set()

    def expand(value, visiting=frozenset(), depth=0):
        if depth > 80:
            raise InvalidArtifact("prepared diagnostic depth exceeds safety bound")
        if type(value) is dict and REFERENCE_KEY in value:
            if not is_reference(value):
                raise InvalidArtifact("invalid prepared diagnostic reference")
            key = value[REFERENCE_KEY]
            row = snapshots.get(key)
            if (key in visiting or row is None or row.get("user_id") != scope["user_id"]
                    or row.get("deck_job_id") != job_id):
                raise InvalidArtifact("missing or foreign prepared diagnostic dependency")
            if key not in expanded:
                _time(row["created_at"])
                result = expand(_decode(row["payload_json"]), visiting | {key}, depth + 1)
                digest = hashlib.sha256((dumps((scope["user_id"], job_id)) + "\n"
                                         + dumps(result)).encode()).hexdigest()
                if digest != key:
                    raise InvalidArtifact("prepared diagnostic checksum mismatch")
                expanded[key] = result
            used.add(key)
            return expanded[key]
        if type(value) is dict:
            return {key: expand(item, visiting, depth + 1) for key, item in value.items()}
        if type(value) is list:
            return [expand(item, visiting, depth + 1) for item in value]
        return value

    expected_candidate = bundle.get("candidate_set")
    if candidate_set is not None and dependency_hash(candidate_set) != dependency_hash(expected_candidate):
        raise InvalidArtifact("candidate set does not match original preparation")
    non_ghosts = [row for row in bundle["impressions"] if row.get("is_ghost") != 1]
    if len(non_ghosts) != len(bundle["cards"]):
        raise InvalidArtifact("incomplete original prepared evidence")
    runtime = {row["impression_id"]: card for row, card in zip(non_ghosts, bundle["cards"])}
    detached = _decode(_encode(rows))
    previous = -1
    for row in detached:
        original = originals.get(row.get("impression_id"))
        if original is None:
            raise InvalidArtifact("impression ID was not reserved by this preparation")
        if row.get("user_id") != scope["user_id"] or row.get("league_id") != scope["league_id"] or row.get("deck_job_id") != job_id:
            raise InvalidArtifact("foreign publication scope")
        immutable = set(original) | set(row)
        immutable -= {"features_json", "served_at"}
        if dependency_hash({key: row.get(key) for key in immutable}) != dependency_hash(
                {key: original.get(key) for key in immutable}):
            raise InvalidArtifact("publication changed prepared terms or attribution")
        if row.get("served_at") != publication.get("served_at"):
            raise InvalidArtifact("publication timestamp differs from original adoption")
        _time(row["served_at"])
        raw = original.get("features_json")
        frozen_features = _decode(raw) if type(raw) is str else raw
        features = expand(frozen_features)
        if type(features) is not dict or type(row.get("features_json")) is not dict:
            raise InvalidArtifact("expanded structured publication features required")
        if original.get("is_ghost") != 1:
            if type(row.get("card_index")) is not int or row["card_index"] <= previous:
                raise InvalidArtifact("publication must preserve original order")
            previous = row["card_index"]
            features.pop("first_deck", None)
            if publication.get("first_deck", False):
                features["first_deck"] = True
            board = publication.get("board_state")
            if board is not None:
                if type(board) is not list or len(board) != 2 or type(board[0]) is not int or board[0] < 0:
                    raise InvalidArtifact("invalid frozen board state")
                features.update(ranked_player_count=board[0], last_board_update_at=board[1],
                                user_value_basis="personal" if board[0] else "consensus")
            if "prepared_runtime" in row["features_json"]:
                features.update(prepared_runtime=runtime[row["impression_id"]],
                                prepared_inventory_id=inventory_id, deck_source="prepared_adoption")
        if dependency_hash(features) != dependency_hash(row["features_json"]):
            raise InvalidArtifact("publication changed frozen evidence")
        # Snapshot IDs bind expanded content, not a batch-local packing shape.
        # Recompacting 30/100-card batches could encode the same ID differently.
        # Preserve the authenticated original DAG and its original timestamps;
        # only the ordinary serve fields above change at actual adoption.
        for key in DIAGNOSTIC_KEYS:
            if key in frozen_features:
                features[key] = frozen_features[key]
        row["features_json"] = dumps(features)
    return detached, expected_candidate, [row for key, row in snapshots.items() if key in used]


def _apply_mutations(conn, data, publication, rows):
    """Consume deferred suppression effects only with their actual publication."""
    payload, scope = data["payload"], data["scope"]
    mutations = payload.get("mutations", [])
    if type(mutations) is not list:
        raise InvalidArtifact("invalid deferred mutations")
    bundle = payload.get("inventory", payload)
    originals = [row for row in bundle.get("impressions", []) if row.get("is_ghost") != 1]
    selected = {row["impression_id"]: row for row in rows if row.get("is_ghost") != 1}
    committed = {card["runtime"]["trade_id"]: selected[row["impression_id"]]
                 for card, row in zip(bundle["cards"], originals)
                 if row["impression_id"] in selected}
    first = not bundle["cards"] or any(row["card_index"] == 0 for row in selected.values())
    fields = {"declined_at", "expires_at", "retested_at", "retest_trade_hash", "lifted_at"}
    table = db.deck_suppressions_table
    for mutation in mutations:
        if (type(mutation) is not dict or type(mutation.get("id")) is not int
                or mutation.get("kind") not in {"resuppress", "retest"}
                or type(mutation.get("before")) is not dict or set(mutation["before"]) != fields):
            raise InvalidArtifact("invalid bound suppression mutation")
        before = mutation["before"]
        after = dict(before)
        if mutation["kind"] == "resuppress":
            if not first:
                continue
            _time(mutation.get("passed_at"))
            _time(mutation.get("expires_at"))
            after.update(declined_at=mutation["passed_at"], expires_at=mutation["expires_at"],
                         retested_at=None, retest_trade_hash=None)
        else:
            trade = committed.get(mutation.get("trade_id"))
            if trade is None:
                continue
            if mutation.get("trade_hash") != trade.get("trade_hash"):
                raise InvalidArtifact("retest must bind the committed exact offer")
            after.update(retested_at=publication["served_at"], retest_trade_hash=mutation["trade_hash"])
        row = conn.execute(select(table).where(table.c.id == mutation["id"],
            table.c.user_id == scope["user_id"], table.c.league_id == scope["league_id"])
            .with_for_update()).mappings().first()
        if row is None:
            raise StaleWork("suppression removed before adoption")
        actual = {key: row[key] for key in fields}
        if dependency_hash(actual) == dependency_hash(after):
            continue  # Exact committed retry, not a second retest opportunity.
        if dependency_hash(actual) != dependency_hash(before):
            raise StaleWork("suppression changed before adoption")
        predicates = [table.c.id == mutation["id"], table.c.user_id == scope["user_id"],
                      table.c.league_id == scope["league_id"]]
        predicates.extend(table.c[key].is_(None) if value is None else table.c[key] == value
                          for key, value in before.items())
        if conn.execute(update(table).where(*predicates).values(**after)).rowcount != 1:
            raise StaleWork("suppression changed during adoption")


def ensure_adoption_evidence(claim: dict, *, candidate_set: dict | None,
                             rows: list[dict], now=None) -> dict[str, int]:
    """Atomically ensure exact candidate, scoped diagnostics and impression rows.

    No shown/activity/like/outcome writes beyond these real adoption evidence
    rows. Original reserved IDs are idempotent ONLY for equal bound content.
    Caller must checkpoint and expose cards after this function commits. This
    store supports only the full original inventory/order, not subset reranking.
    """
    table, stamp = db.prepared_trade_inventories_table, _iso(now)
    with db.engine.connect() as conn:
        initial = conn.execute(select(table).where(table.c.inventory_id == claim["inventory_id"])).mappings().first()
    if not initial:
        raise StaleWork("prepared inventory no longer exists")
    try:
        scope = _scope(_decode(_artifact_text(initial))["scope"])
    except (KeyError, TypeError) as exc:
        raise InvalidArtifact("invalid prepared scope") from exc
    data = _verified(initial, scope, now)
    if not data or data["participants"] != claim["participants"]:
        raise StaleWork("prepared artifact no longer matches adoption")
    with _work(data["participants"], claim["work_started"]), db.engine.begin() as conn:
        if not _index_matches(conn, data):
            raise InvalidArtifact("incomplete participant deletion index")
        identities = _identity_receipt(conn, data["participants"], scope.user_id)
        if dependency_hash(identities) != dependency_hash(data["identity_receipt"]):
            raise StaleWork("account lifetime changed before publication")
        current = conn.execute(select(table).where(table.c.inventory_id == claim["inventory_id"],
            table.c.payload_sha256 == claim["payload_sha256"], table.c.adoption_token == claim["token"],
            table.c.adoption_lease_until > stamp, table.c.expires_at > stamp).with_for_update()).mappings().first()
        if not current or dependency_hash(_decode(current["adoption_json"])) != dependency_hash(claim["publication"]):
            raise StaleWork("adoption claim or immutable publication changed")
        bound_rows, expected_candidate, snapshots = _adoption_rows(data, claim["publication"],
            claim["inventory_id"], candidate_set, rows)
        counts = {"candidate_sets": 0, "snapshots": 0, "impressions": 0}
        if candidate_set is not None:
            counts["candidate_sets"] = _ensure_exact_rows(conn, db.deck_candidate_sets_table,
                                                           "candidate_set_id", [candidate_set])
        if expected_candidate is not None:
            existing = conn.execute(select(db.deck_candidate_sets_table).where(
                db.deck_candidate_sets_table.c.candidate_set_id == expected_candidate["candidate_set_id"])).mappings().first()
            if existing is None or dependency_hash({str(k): v for k, v in existing.items()}) != dependency_hash(
                    _db_row(db.deck_candidate_sets_table, expected_candidate)):
                raise InvalidArtifact("candidate dependency not durably available")
        counts["snapshots"] = _ensure_exact_rows(conn, db.deck_diagnostic_snapshots_table,
                                                "snapshot_id", snapshots)
        counts["impressions"] = _ensure_exact_rows(conn, db.deck_impressions_table,
                                                  "impression_id", bound_rows)
        _apply_mutations(conn, data, claim["publication"], bound_rows)
        return counts


def invalidate_inventory(scope: InventoryScope) -> int:
    scope = _scope(scope)
    with db.engine.begin() as conn:
        ids = conn.execute(select(db.prepared_trade_inventories_table.c.inventory_id).where(
            db.prepared_trade_inventories_table.c.scope_key == scope.key)).scalars().all()
        return _drop_subjects(conn, "inventory", ids)


def prune(*, now=None) -> int:
    """Delete expired disposable artifacts and their participant index only."""
    with db.engine.begin() as conn:
        ids = conn.execute(select(db.prepared_trade_inventories_table.c.inventory_id).where(
            db.prepared_trade_inventories_table.c.expires_at <= _iso(now))).scalars().all()
        return _drop_subjects(conn, "inventory", ids)


def sweep_status(sweep_id: str, *, now=None) -> dict | None:
    """Aggregate only. Unexpired is not synonymous with source-revalidated fresh."""
    sweeps, targets, inventories = db.prepared_trade_sweeps_table, db.prepared_trade_targets_table, db.prepared_trade_inventories_table
    with db.engine.connect() as conn:
        sweep = conn.execute(select(sweeps).where(sweeps.c.sweep_id == sweep_id)).mappings().first()
        if not sweep:
            return None
        counts = dict(conn.execute(select(targets.c.status, func.count()).where(
            targets.c.sweep_id == sweep_id).group_by(targets.c.status)).all())
        unexpired = conn.execute(select(func.count()).select_from(targets.join(inventories,
            targets.c.inventory_id == inventories.c.inventory_id)).where(
                targets.c.sweep_id == sweep_id, inventories.c.expires_at > _iso(now))).scalar_one()
        next_retry = conn.execute(select(func.min(targets.c.available_at)).where(
            targets.c.sweep_id == sweep_id, targets.c.status == "pending")).scalar_one()
        remaining = counts.get("pending", 0) + counts.get("running", 0)
        status = "complete" if sweep["status"] == "running" and not remaining else sweep["status"]
        return {"sweep_id": sweep_id, "status": status, "created_at": sweep["created_at"],
                "updated_at": sweep["updated_at"], "target_count": sweep["target_count"],
                "deleted_count": sweep["deleted_count"], "counts": counts,
                "coverage": _decode(sweep["coverage_json"]),
                "remaining_count": remaining, "next_retry_at": next_retry,
                "unexpired_artifacts": unexpired, "freshness_requires_source_revalidation": True}


def resumable_sweeps(*, now=None) -> list[str]:
    """Oldest-first durable unfinished sweeps, including delayed/expired claims.

    Includes future retries so the scheduler does not start a competing hourly
    cohort. claim_target enforces availability and lease expiry. Stops excluded.
    `now` is accepted for scheduler API symmetry; this is not a due-only query.
    """
    sweeps, targets = db.prepared_trade_sweeps_table, db.prepared_trade_targets_table
    with db.engine.connect() as conn:
        pending = select(targets.c.target_id).where(targets.c.sweep_id == sweeps.c.sweep_id,
            targets.c.status.in_(("pending", "running"))).exists()
        return list(conn.execute(select(sweeps.c.sweep_id).where(sweeps.c.status == "running", pending)
                                .order_by(sweeps.c.created_at, sweeps.c.sweep_id)).scalars())


def stop_sweep(sweep_id: str, *, now=None) -> bool:
    """Revoke running tokens and cancel remaining targets, retaining ready data."""
    sweeps, targets = db.prepared_trade_sweeps_table, db.prepared_trade_targets_table
    with db.engine.begin() as conn:
        conn.execute(select(db.prepared_trade_worker_table).with_for_update()).all()
        tokens = conn.execute(select(targets.c.lease_token).where(targets.c.sweep_id == sweep_id,
            targets.c.status == "running")).scalars().all()
        changed = conn.execute(update(sweeps).where(sweeps.c.sweep_id == sweep_id,
            sweeps.c.status == "running").values(status="stopped", updated_at=_iso(now))).rowcount
        conn.execute(update(targets).where(targets.c.sweep_id == sweep_id,
            targets.c.status.in_(("running", "pending"))).values(status="cancelled", reason="stopped",
                lease_token=None, lease_until=None, updated_at=_iso(now)))
        for token in tokens:
            _release_worker(conn, token)
        return bool(changed)


def delete_for_users(conn, user_ids) -> dict[str, int]:
    """Called INSIDE account deletion's transaction after its alias row locks.

    Remove entire disposable artifacts/targets containing any deleted actor;
    never anonymize/rewrite a package or retain their private board in another
    owner's cache. Initial sweep denominator remains, without deleted identities.
    """
    ids = sorted(set(user_ids))
    conn.execute(select(db.prepared_trade_worker_table).with_for_update()).all()
    actors, targets, inventories = db.prepared_trade_participants_table, db.prepared_trade_targets_table, db.prepared_trade_inventories_table
    target_ids = set(conn.execute(select(actors.c.subject_id).where(actors.c.subject_kind == "target",
        actors.c.participant_user_id.in_(ids))).scalars())
    target_ids.update(conn.execute(select(targets.c.target_id).where(targets.c.user_id.in_(ids))).scalars())
    inventory_ids = set(conn.execute(select(actors.c.subject_id).where(actors.c.subject_kind == "inventory",
        actors.c.participant_user_id.in_(ids))).scalars())
    inventory_ids.update(conn.execute(select(inventories.c.inventory_id).where(inventories.c.user_id.in_(ids))).scalars())
    affected_sweeps = set()
    for start in range(0, len(target_ids), INSERT_CHUNK):
        chunk = sorted(target_ids)[start:start + INSERT_CHUNK]
        rows = conn.execute(select(targets.c.sweep_id, targets.c.lease_token).where(targets.c.target_id.in_(chunk))).all()
        for sweep_id, token in rows:
            affected_sweeps.add(sweep_id)
            if token:
                _release_worker(conn, token)
            sweeps = db.prepared_trade_sweeps_table
            conn.execute(update(sweeps).where(sweeps.c.sweep_id == sweep_id)
                         .values(deleted_count=sweeps.c.deleted_count + 1))
    counts = {"prepared_trade_inventories_deleted": _drop_subjects(conn, "inventory", inventory_ids),
              "prepared_trade_targets_deleted": _drop_subjects(conn, "target", target_ids)}
    for sweep_id in affected_sweeps:
        _finish_sweep(conn, sweep_id, _iso())
    return counts
