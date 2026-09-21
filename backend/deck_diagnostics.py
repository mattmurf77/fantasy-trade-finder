"""Bounded debug evidence for decks; core features and valuations stay inline.

Large repeated JSON subtrees are interned within one user's generation job.
References are lossless during retention; expiry is explicit on diagnostic reads.
This leaf module performs no database access and never imports the application.
"""
from collections import Counter
import hashlib
import json

DIAGNOSTIC_KEYS = ('owner_request', 'owner_experiment', 'owner_generation',
                   'roster_evaluation')
REFERENCE_KEY = '$deck_diagnostic_v1'
MIN_SHARED_BYTES = 1024


def dumps(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      default=str)


def is_reference(value):
    return (isinstance(value, dict) and set(value) == {REFERENCE_KEY}
            and isinstance(value[REFERENCE_KEY], str))


def compact_rows(rows):
    """Return detached impression rows and unique, user/job-scoped snapshots.

    Only named debug fields change. Canonical JSON hashes preserve every value;
    a subtree is shared only if repeated and >=1 KiB. Roots live separately so
    retention can expire debug detail without deleting impressions or labels.
    Already-normalized and malformed historical JSON is left untouched.
    The synchronous writer may pass a structured features dict instead of a
    JSON string. JSON-compatible immutable nodes remain shared until packing;
    tuples, non-string keys and default=str values follow the former JSON
    round trip. No source object is mutated.
    """
    counts = Counter()
    parsed = []
    identities = {}
    scope_prefixes = {}
    normalized = {}
    normalizing = set()

    def json_ready(value):
        # Normalize only changed nodes, once per actual source identity. This
        # preserves captured sharing without broad content-based interning.
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        key = id(value)
        if key in normalized:
            return normalized[key][1]
        if key in normalizing:
            raise ValueError('Circular reference detected')
        normalizing.add(key)
        if isinstance(value, dict):
            result = {}
            changed = False
            for k, child in value.items():
                name = k if isinstance(k, str) else next(iter(json.loads(json.dumps({k: None}))))
                item = json_ready(child)
                result[name] = item
                changed |= name is not k or item is not child
            if not changed:
                result = value
        elif isinstance(value, (list, tuple)):
            result = [json_ready(child) for child in value]
            if isinstance(value, list) and all(a is b for a, b in zip(result, value)):
                result = value
        else:
            result = str(value)
        normalizing.remove(key)
        normalized[key] = (value, result)  # retain originals against id reuse
        return result

    def identity(scope, value):
        key = (scope, id(value))
        if key in identities:
            return identities[key]
        raw = dumps(value)
        if scope not in scope_prefixes:
            scope_prefixes[scope] = dumps(scope) + '\n'
        digest = hashlib.sha256((scope_prefixes[scope] + raw).encode()).hexdigest()
        identities[key] = (digest, len(raw))
        return identities[key]

    def count(scope, value):
        if not isinstance(value, (dict, list, tuple)) or is_reference(value):
            return
        digest, size = identity(scope, value)
        if size < MIN_SHARED_BYTES:
            return
        counts[digest] += 1
        # A repeated parent is stored once. Walking its identical descendants
        # again cannot save any additional copies of that parent's payload.
        if counts[digest] > 1:
            return
        for child in (value.values() if isinstance(value, dict) else value):
            count(scope, child)

    for row in rows:
        raw = row.get('features_json')
        if isinstance(raw, dict):
            features = dict(json_ready(raw))
        else:
            try:
                features = json.loads(raw or 'null')
            except (ValueError, TypeError):
                features = None
        scope = (row['user_id'], row['deck_job_id'])
        parsed.append((row, features, scope))
        if isinstance(features, dict):
            for key in DIAGNOSTIC_KEYS:
                count(scope, features.get(key))

    snapshots = {}

    def pack(scope, created_at, value, root=False):
        if is_reference(value) or not isinstance(value, (dict, list, tuple)):
            return value
        digest, size = identity(scope, value)
        shared = counts[digest] > 1
        if (root or shared) and digest in snapshots:
            return {REFERENCE_KEY: digest}
        if size < MIN_SHARED_BYTES and not root:
            return value
        packed = ({k: pack(scope, created_at, v) for k, v in value.items()}
                  if isinstance(value, dict)
                  else [pack(scope, created_at, v) for v in value])
        if not (root or shared):
            return packed
        snapshots[digest] = {
            'snapshot_id': digest, 'user_id': scope[0], 'deck_job_id': scope[1],
            'created_at': created_at, 'payload_json': dumps(packed),
        }
        return {REFERENCE_KEY: digest}

    compacted = []
    for original, features, scope in parsed:
        row = dict(original)
        changed = False
        if isinstance(features, dict):
            for key in DIAGNOSTIC_KEYS:
                value = features.get(key)
                if isinstance(value, (dict, list, tuple)) and not is_reference(value):
                    features[key] = pack(scope, row['served_at'], value, root=True)
                    changed = True
            if changed:
                row['features_json'] = dumps(features)
            elif isinstance(original.get('features_json'), dict):
                row['features_json'] = json.dumps(features, default=str)
        compacted.append(row)
    return compacted, list(snapshots.values())


def expand_features(features, snapshots):
    """Reconstruct debug fields from a scoped snapshot map, explicitly marking gaps."""
    def expand(value, visiting):
        if is_reference(value):
            sid = value[REFERENCE_KEY]
            if sid in visiting:
                raise ValueError('cyclic deck diagnostic reference')
            if sid not in snapshots:
                return {'diagnostic_status': 'expired_or_missing', 'snapshot_id': sid}
            return expand(json.loads(snapshots[sid]), visiting | {sid})
        if isinstance(value, dict):
            return {k: expand(v, visiting) for k, v in value.items()}
        if isinstance(value, list):
            return [expand(v, visiting) for v in value]
        return value
    return expand(features, set())
