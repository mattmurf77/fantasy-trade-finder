"""Compact full-position public metadata for Calibration, separate from pricing.

Only capture may refresh. Currentness reads the durable atomic snapshot without
network I/O. Frozen consumed facts survive deployment in private source; missing
local cache is not a new provider observation. No catalog is
stored per comparison and no data enters the ordinary ranking/player pipeline.
"""
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
import fcntl
import hashlib
import json
import math
import os
import tempfile
import time
from .blind_grading import GradingError

FIELDS = ('player_id','position','fantasy_positions','active','injury_status')
URL = 'https://api.sleeper.app/v1/players/nfl'
TTL_SECONDS = 20 * 3600
MAX_ROWS = 50000
MAX_BYTES = 20 * 1024 * 1024
SCHEMA = 'calibration-full-position-metadata-1'
CACHE_PATH = (Path(tempfile.gettempdir()) / f'ftf-calibration-metadata-test-{os.getpid()}.json'
              if os.environ.get('FTF_TEST_MODE') == '1' else
              Path(__file__).resolve().parent.parent / 'data' / '.calibration_roster_metadata.json')
_lock = Lock()


def _digest(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',',':')).encode()).hexdigest()


def peek():
    """No fetch; absent/corrupt durable evidence is not silently called current."""
    try:
        if CACHE_PATH.stat().st_size > MAX_BYTES:
            return None
        result = json.loads(CACHE_PATH.read_text())
        if (result.get('schema') != SCHEMA or not isinstance(result.get('rows'),dict)
                or len(result['rows']) > MAX_ROWS or result.get('revision') != _digest(result['rows'])
                or isinstance(result.get('observed_at'),bool)
                or not isinstance(result.get('observed_at'),(int,float))
                or not math.isfinite(result['observed_at'])):
            return None
        return result
    except (OSError,ValueError,TypeError,AttributeError):
        return None


def capture(fetch):
    """Cross-process coalesced refresh, preserving prior complete file on error."""
    with _lock:
        CACHE_PATH.parent.mkdir(parents=True,exist_ok=True)
        with CACHE_PATH.with_suffix('.lock').open('a') as lockfile:
            fcntl.flock(lockfile,fcntl.LOCK_EX)
            old=peek()
            if old and 0 <= time.time()-old['observed_at'] < TTL_SECONDS:
                return old
            try:
                raw=fetch(URL)
            except Exception:
                raise GradingError('player_metadata_unavailable',503) from None
            if not isinstance(raw,dict) or not raw or len(raw)>MAX_ROWS:
                raise GradingError('player_metadata_unavailable',409)
            rows={}
            for pid,row in raw.items():
                if not isinstance(pid,str) or not isinstance(row,dict):
                    raise GradingError('player_metadata_unavailable',409)
                rows[pid]={k:row.get(k) for k in FIELDS}
            observed=time.time()
            result={'schema':SCHEMA,'observed_at':observed,'revision':_digest(rows),'rows':rows}
            encoded=json.dumps(result,sort_keys=True,separators=(',',':'))
            if len(encoded.encode())>MAX_BYTES:
                raise GradingError('player_metadata_unavailable',409)
            tmp=None
            try:
                with tempfile.NamedTemporaryFile(mode='w',dir=CACHE_PATH.parent,prefix=CACHE_PATH.name+'.',delete=False) as handle:
                    tmp=Path(handle.name);handle.write(encoded);handle.flush();os.fsync(handle.fileno())
                os.replace(tmp,CACHE_PATH)
            finally:
                if tmp is not None:tmp.unlink(missing_ok=True)
            return result


def observation(snapshot, ids):
    """Only consumed held rows survive in the private frozen comparison."""
    return {'schema':SCHEMA, 'observed_at':snapshot['observed_at'],
            'held':{pid:snapshot['rows'].get(pid) for pid in sorted(set(ids))}}


def held_identity(captured, *, captured_only=False):
    """Frozen as-of fallback; only a newer valid observation can supersede it.

    Deployment cache absence is not a provider change. A newer snapshot's
    missing row IS a known change, so it replaces the earlier row with None.
    """
    latest = None if captured_only else peek()
    newer = latest and latest['observed_at'] >= captured['observed_at']
    rows = ({pid:latest['rows'].get(pid) for pid in captured['held']} if newer else captured['held'])
    return {'schema':SCHEMA,'held':rows}


def manifest(snapshot,ids):
    return {'schema':SCHEMA,'source':'sleeper_players_nfl_full_positions',
            'observed_at':datetime.fromtimestamp(snapshot['observed_at'],timezone.utc).isoformat(),
            'held_count':len(set(ids)), 'held_fields':list(FIELDS),
            'held_hash':_digest({pid:snapshot['rows'].get(pid) for pid in sorted(set(ids))}),
            'normal_ranking_pool_expanded':False}
