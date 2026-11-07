"""Synthetic CPU/memory measurement, not source accuracy or hosted p95 evidence.

Run from root: PYTHONPATH=. python3 docs/plans/league-projections/benchmark-synthetic.py
"""
from pathlib import Path
import hashlib
import json
import platform
import resource
import sys
import time
from backend.league_projections.simulation import simulate

teams = [dict(roster_id=i, name=f"Synthetic team {i}", wins=4, losses=4, ties=0,
              points_for="160", points_against="160", maxpf="200",
              actual_history=["10", "30"] * 4, maxpf_history=[]) for i in range(1, 13)]
weeks = [dict(week=w, games=[[i, i + 1] for i in range(1, 13, 2)],
              teams={str(i): dict(actual={"points": str(15 + i)}, maxpf={"points": str(22 + i)},
                                 maxpf_dominates_actual=True) for i in range(1, 13)}) for w in range(9, 15)]
snapshot = dict(teams=teams, weeks=weeks, completed_weeks=8, playoff_spots=6, playoff_byes=2,
                pick_ownership=[], source="synthetic_performance_only", captured_at="2026-11-06T12:00:00+00:00")
config = dict(seeding="record_pf_higher_pa_random", draft_tie="random_exact_ties", ir_maxpf="include",
              reserve_activation="exclude_current_reserve", empty_slots="fill_available", maxpf_variance="actual_history_proxy",
              iterations=250000, seed=730, historical_weight=.6, persistent_sd=5, residual_correlation=.5)
root = Path(__file__).resolve().parents[3]
source_hashes = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in (root / "backend/league_projections").glob("*.py")}
started = time.monotonic()
result = simulate(snapshot, config)
elapsed = time.monotonic() - started
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(json.dumps({"synthetic_only": True, "python": platform.python_version(), "platform": platform.platform(),
                  "iterations": 250000, "teams": 12, "future_games": 36, "wall_seconds": round(elapsed, 3),
                  "peak_rss_bytes": rss if sys.platform == "darwin" else rss * 1024,
                  "source_sha256": source_hashes, "snapshot_hash": result["snapshot_hash"],
                  "playoff_sum": sum(t["playoff_probability"] for t in result["teams"]),
                  "pick_column_sums": [sum(t["pick_probabilities"][k] for t in result["teams"]) for k in range(6)]}, indent=2))
