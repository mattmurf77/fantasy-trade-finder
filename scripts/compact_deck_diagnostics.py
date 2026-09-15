"""Resumable storage maintenance; dry-run unless --apply and a backup are supplied.

Never imports server or initializes the whole schema. Reads DATABASE_URL from
its process environment; callers must load secrets without printing them.
Updates only features_json, preserving every core field and exact diagnostics.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def compact_batch(conn, rows):
    from sqlalchemy import update
    from backend import database as db
    from backend.deck_diagnostics import compact_rows, expand_features
    compacted, snapshots = compact_rows(rows)
    mapping = {s['snapshot_id']: s['payload_json'] for s in snapshots}
    changes = []
    for old, new in zip(rows, compacted):
        if old['features_json'] == new['features_json']:
            continue
        # Validate each conversion before any write; values/structure, not formatting.
        if expand_features(json.loads(new['features_json']), mapping) != json.loads(old['features_json']):
            raise ValueError('diagnostic roundtrip mismatch; batch not applied')
        changes.append((old, new))
    db._save_deck_diagnostic_snapshots(conn, snapshots)
    for old, new in changes:
        result = conn.execute(update(db.deck_impressions_table).where(
            db.deck_impressions_table.c.impression_id == old['impression_id'],
            db.deck_impressions_table.c.features_json == old['features_json']).values(
                features_json=new['features_json']))
        if result.rowcount != 1:
            raise ValueError('impression changed during maintenance; batch rolled back')
    return len(changes), len(snapshots)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--backup-path', type=Path)
    parser.add_argument('--backup-sha256')
    parser.add_argument('--batch-size', type=int, default=100)
    parser.add_argument('--max-batches', type=int, default=1)
    parser.add_argument('--after', default='')
    parser.add_argument('--after-job', default='')
    args = parser.parse_args()
    if not os.environ.get('DATABASE_URL'):
        parser.error('DATABASE_URL must be explicitly configured')
    if not 1 <= args.batch_size <= 100 or not 1 <= args.max_batches <= 2000:
        parser.error('batch size must be 1..100; max batches 1..2000')
    if args.apply:
        if not args.backup_path or not args.backup_sha256:
            parser.error('--apply requires --backup-path and --backup-sha256')
        if not args.backup_path.is_file():
            parser.error('backup does not exist')
        with args.backup_path.open('rb') as f:
            digest = hashlib.file_digest(f, 'sha256').hexdigest()
        if digest != args.backup_sha256:
            parser.error('backup checksum mismatch')
    from sqlalchemy import select, text, or_, and_
    from backend import database as db
    from backend.deck_diagnostics import compact_rows
    if args.apply:
        # Add only the dedicated table. No app init, model seeds or migrations.
        db.deck_diagnostic_snapshots_table.create(db.engine, checkfirst=True)
    i = db.deck_impressions_table
    cursor = args.after
    job_cursor = args.after_job
    changed = scanned = nodes = 0
    for _ in range(args.max_batches):
        with db.engine.begin() as conn:
            if conn.dialect.name == 'postgresql':
                conn.execute(text("SET LOCAL statement_timeout = '15s'"))
                conn.execute(text("SET LOCAL lock_timeout = '2s'"))
                if not args.apply:
                    conn.execute(text('SET TRANSACTION READ ONLY'))
            query = select(i).where(or_(i.c.deck_job_id > job_cursor, and_(
                i.c.deck_job_id == job_cursor, i.c.impression_id > cursor))).order_by(
                    i.c.deck_job_id, i.c.impression_id).limit(args.batch_size)
            if args.apply:
                query = query.with_for_update()
            batch = [dict(r._mapping) for r in conn.execute(query)]
            if not batch:
                break
            if args.apply:
                n, sn = compact_batch(conn, batch)
            else:
                compacted, snapshots = compact_rows(batch)
                n = sum(a['features_json'] != b['features_json'] for a,b in zip(batch,compacted))
                sn = len(snapshots)
            changed += n
            nodes += sn
            scanned += len(batch)
            cursor = batch[-1]['impression_id']
            job_cursor = batch[-1]['deck_job_id']
        # Cursor contains a random impression ID, never a user identifier/payload.
        print(json.dumps({'apply':args.apply,'scanned':scanned,'changed':changed,
                          'snapshot_candidates':nodes,'after':cursor,'after_job':job_cursor}), flush=True)
    db.engine.dispose()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # SQLAlchemy exceptions embed SQL parameters / private JSON. Suppress them.
        print(json.dumps({'error': type(exc).__name__, 'message': 'Batch failed; transaction rolled back. Resume from last successful cursor.'}), file=sys.stderr)
        sys.exit(1)
