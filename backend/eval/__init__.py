"""backend.eval — F8 Offline Eval Harness (replay/IPS + calibration).

Operator tooling, unflagged (no user surface, no server wiring this wave).
docs/plans/tiktok-discovery/prds/F8-offline-eval.md.

Modules:
  data        — load the F1 impression spine (deck_impressions ⨝ deck_outcomes)
                into replayable deck structures
  scorers     — registered-scorer registry (production baseline, logged order,
                base_score, random canary) + the Scorer protocol future
                candidates (F6) implement
  replay      — the IPS/SNIPS replay evaluator + operator CLI
                (python3 -m backend.eval.replay --help)
  calibration — reliability tables by predicted-probability decile for
                probability-emitting scorers (F6)
  persistence — append-only JSON-lines run records under data/eval_runs/
  nightly     — run_all(): re-run every registered scorer on the trailing
                window (idempotent per day); server cron hook is a HANDOFF,
                not wired here
  flip_read   — the model-side 24 h read after the 200 ms flip (G1-G3,
                G7-G10, the weekly U4-R4 / B4 ceilings), read-only
                (python3 -m backend.eval.flip_read --help)
  bdk_audit   — the B-DK-4..7 production audit: served violations of
                deck.quality_filters' rules against a bar of 0, read-only
                (python3 -m backend.eval.bdk_audit --help)
  synth       — synthetic logged-data generator for demos + the CLI
                end-to-end check

Read-only against product tables: this package never writes to
deck_impressions/deck_outcomes or any other product table. Its only writes
are JSON files under the (already gitignored) data/eval_runs/ directory.
"""
