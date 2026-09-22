# Read-only production capacity check — 2026-09-22

One authenticated Render `GET /v1/services/srv-d7g37ftckfvc73a32gvg`
returned web service, Python runtime, Oregon, one instance, legacy `standard`
plan, not suspended, and `autoDeploy=no`. No API mutation, plan upgrade, deploy
or configuration change was made. The initial sandbox network attempt failed;
the explicitly approved GET-only retry succeeded. The script prints only
allowlisted capacity metadata, never its credential.

Render's current [compute-plan documentation](https://render.com/docs/compute-plans)
maps legacy `standard` to `1c-2g`: **1 CPU, 2 GB RAM per instance**. This is a
capacity fact, not a measurement of free memory or actual load. Local macOS
Python3.14/SQLite timings and process RSS cannot be relabeled Render throughput
or PostgreSQL latency. Multiple concurrent search threads share this capacity;
per-request caches require a memory/lifetime bound and contention evidence.

No paid infrastructure change is proposed or authorized by this readback.
Continue code/model/preparation improvements first; verify exact service state
again before any eventual release.
