"""Initialize backend imports with a scratch DB and blocked external requests."""
import os
from pathlib import Path
import sys
import tempfile
import urllib.request

REPO = Path(__file__).resolve().parents[4]


def bootstrap():
    os.chdir(REPO)
    sys.path.insert(0, str(REPO))
    scratch = tempfile.mkdtemp(prefix='ftf-security-import-')
    os.environ['DATABASE_URL'] = 'sqlite:///' + str(Path(scratch) / 'import.sqlite')
    os.environ['ANTHROPIC_API_KEY'] = ''
    fixture = str(REPO / 'backend/tests/fixtures/dp_values_picks_2026-08-06.csv')
    os.environ['FTF_DP_VALUES_FILE'] = fixture
    os.environ['FTF_DP_PICK_VALUES_FILE'] = fixture
    def blocked(*args, **kwargs):
        raise RuntimeError('External network disabled; mock the upstream boundary')
    urllib.request.urlopen = blocked
    import backend.server
    # Preserve suite player-data mocks; only startup requires this player seam.
    os.environ.pop('FTF_DP_VALUES_FILE', None)
