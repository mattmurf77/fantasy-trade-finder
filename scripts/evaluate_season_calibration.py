#!/usr/bin/env python3
"""Offline historical Win Now readiness and conditional calibration report.

Prediction/checkpoint JSON contracts: backend.season_calibration module docstring.
Omitting --predictions reports the actual missing archived-forecast evidence.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.season_calibration import evaluate_calibration


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outcomes", type=Path, required=True)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--checkpoints", type=Path, help="Reviewed historical kickoff boundaries and evidence citations")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=1701)
    args = parser.parse_args()
    try:
        read = lambda path: json.loads(path.read_text()) if path else None
        result = evaluate_calibration(read(args.outcomes), read(args.predictions), read(args.checkpoints),
                                      bootstrap_samples=args.bootstrap_samples, seed=args.seed)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(2, f"Evaluation failed: {exc}\n")
    counts = {key: value for key, value in result["availability"].items() if isinstance(value, int)}
    print(json.dumps({"status": result["status"], "availability": counts,
                      "report": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
