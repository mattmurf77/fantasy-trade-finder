"""Full backend suite under Python3.12 with isolated, network-disabled startup."""
import sys
if sys.version_info[:2] != (3, 12):
    raise SystemExit('Run this harness with Python3.12')
from runtime_bootstrap import bootstrap
bootstrap()
import pytest
raise SystemExit(pytest.main(['backend/tests', '-q', '--tb=short'] + sys.argv[1:]))
