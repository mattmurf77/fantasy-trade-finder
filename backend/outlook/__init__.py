"""Componentized playoff / championship odds pipeline (feedback #169).

Five swappable phases, each behind a `typing.Protocol`, wired from config via
registries in `pipeline.py`. Nothing downstream imports a concrete provider —
only the Protocols + factories. See odds-pipeline-lld.md.

    Phase 1  league_state.py   LeagueStateProvider   (schedule + standings)
    Phase 2  strength.py       StrengthProvider      (mu/sigma per team)  ← key swap seam
    Phase 3  simulator.py      Simulator             (seeded Monte-Carlo)
    Phase 4  playoff_format.py PlayoffFormat         (seeding/byes/bracket)
    Phase 5  serialize.py      OutlookSerializer      (fixed payload)
"""

from .pipeline import build_league_state, run_outlook

__all__ = ["build_league_state", "run_outlook"]
