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
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def is_reference(value):
    return (isinstance(value, dict) and set(value) == {REFERENCE_KEY}
            and isinstance(value[REFERENCE_KEY], str))


def compact_rows(rows):
    """Return detached impression rows and unique, user/job-scoped snapshots.

    Only named debug fields change. Canonical JSON hashes preserve every value;
    a subtree is shared only if repeated and >=1 KiB. Roots live separately so
    retention can expire debug detail without deleting impressions or labels.
    Already-normalized and malformed historical features are left untouched.
    """
    counts = Counter()
    parsed = []

    def identity(scope, value):
        raw = dumps(value)
        digest = hashlib.sha256((dumps(scope) + '\n' + raw).encode()).hexdigest()
        return digest, raw

    def count(scope, value):
        if not isinstance(value, (dict, list)) or is_reference(value):
            return
        digest, raw = identity(scope, value)
        if len(raw) < MIN_SHARED_BYTES:
            return
        counts[digest] += 1
        for child in (value.values() if isinstance(value, dict) else value):
            count(scope, child)

    for row in rows:
        try:
            features = json.loads(row.get('features_json') or 'null')
        except (ValueError, TypeError):
            features = None
        scope = (row['user_id'], row['deck_job_id'])
        parsed.append((row, features, scope))
        if isinstance(features, dict):
            for key in DIAGNOSTIC_KEYS:
                count(scope, features.get(key))

    snapshots = {}

    def pack(scope, created_at, value, root=False):
        if is_reference(value) or not isinstance(value, (dict, list)):
            return value
        digest, raw = identity(scope, value)
        shared = counts[digest] > 1
        if (root or shared) and digest in snapshots:
            return {REFERENCE_KEY: digest}
        if len(raw) < MIN_SHARED_BYTES and not root:
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
                if isinstance(value, (dict, list)) and not is_reference(value):
                    features[key] = pack(scope, row['served_at'], value, root=True)
                    changed = True
            if changed:
                row['features_json'] = dumps(features)
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
