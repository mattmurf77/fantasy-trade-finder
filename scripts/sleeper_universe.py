"""Sleeper trade universe research crawler -- entry point.

Logic lives in backend/sleeper_universe/ (importable, tested by
backend/tests/test_sleeper_universe_*.py). Usage and what is stored:
backend/sleeper_universe/README.md. Public Sleeper REST v1 reads only, one
throttled client; writes only data/sleeper-universe/ (git-ignored).

    python3 scripts/sleeper_universe.py run --cap 150   # pilot: ~150 lineages, 2024-2026, ~21,000 requests
    python3 scripts/sleeper_universe.py run             # full pull / resume
    python3 scripts/sleeper_universe.py report
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.sleeper_universe.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
