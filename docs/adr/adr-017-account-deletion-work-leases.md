# ADR-017 — Drain account work before deleting its data

**Date:** 2026-09-04
**Status:** Deployed 2026-09-05 (PR #279; D-183)

## Context

Deleting rows and sessions does not stop already-authorized requests or queued background jobs from recreating them. The deployed service uses one gunicorn worker; cron services invoke its HTTP handlers. Normal account requests must remain concurrent with background generation.

## Decision

`user_data_lifecycle` gives ordinary work shared admissions and account deletion exclusive access. Requests retain resolved-user admissions until teardown. Session initialization and trade generation capture a generation before scheduling; identity resolution and notification scans use a revision captured before their inputs are read. Deletion stops new admissions, drains active operations, rechecks aliases, commits the deletion, then invalidates old generations. Fresh work after deletion can register a new account.

Alias locks use a stable order, with a ten-second total drain deadline. A timeout fails deletion without partially deleting rows. Synchronous child work remains admitted while its parent is draining. Session restoration and persistence retain their separate lock, acquired after account work has drained.

Linked provider identities participate through namespaced hashes, acquired before identity lookup. This prevents a delayed Apple or Google proof from recreating an account after deletion removed its identity mapping. Background work carries its original revision into nested work, including writes for a counterparty; starting that nested operation later does not make a pre-deletion task fresh.

Receipt grading also checks that the originating owned impression still exists before inserting a grade, so stale batches cannot reconstruct deleted recommendations.

## Limits and consequences

This coordinates one worker process. Scaling to multiple workers, independent cron writers or maintenance scripts requires distributed fencing before deployment. Restarting the one worker terminates its queued work; there is no durable task queue to resume. Public league imports and records belonging to other managers remain subject to the documented retention policy.

The module retains per-identity generations in memory for the worker lifetime so delayed work cannot become valid again. Active long-running work can require the user to retry deletion. No schema or dependency is added.

## Evidence

`test_user_data_lifecycle.py` exercises simultaneous work, draining, timeout recovery, stale identity resolution, HTTP writes and queued generation. The security PostgreSQL harness runs these and the transaction/session-deletion regressions against isolated synthetic schemas. See the [combined review](../plans/security-data-hardening/review.md).
