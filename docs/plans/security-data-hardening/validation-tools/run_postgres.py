"""Opt-in synthetic PostgreSQL validation; run with --help for invocation."""
import argparse
import os
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--database-url-env', required=True,
                    help='Name of env var containing explicit LOCAL synthetic PostgreSQL URL')
parser.add_argument('--confirm-synthetic', required=True, action='store_true',
                    help='Confirm target database is disposable test data, never production')
args = parser.parse_args()
from pg_validation_support import configure, isolated_engine, cleanup
try:
    configure(os.environ[args.database_url_env])
except Exception:
    parser.exit(2, 'Invalid or missing local synthetic database configuration.\n')
from runtime_bootstrap import bootstrap
bootstrap()
import pytest
from backend import database as db
from backend.tests import test_outcome_ingest_security as outcomes
from backend.tests import test_account_deletion_coverage as deletion
from backend.tests import test_user_data_lifecycle as lifecycle
from backend.tests import test_deletion_session_races as races
outcomes.create_engine = isolated_engine
deletion.create_engine = isolated_engine
lifecycle.create_engine = isolated_engine
races.create_engine = isolated_engine
# The helpers branch on dialect via DATABASE_URL; no credentials are read here.
db.DATABASE_URL = 'postgresql://synthetic-validation'
try:
    code = pytest.main(['backend/tests/test_outcome_ingest_security.py',
                        'backend/tests/test_account_deletion_coverage.py',
                        'backend/tests/test_user_data_lifecycle.py',
                        'backend/tests/test_deletion_session_races.py',
                        str(Path(__file__).with_name('test_postgres_security.py')),
                        '-q', '--tb=short'])
finally:
    cleanup()
raise SystemExit(code)
