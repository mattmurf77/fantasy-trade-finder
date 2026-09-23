# ADR-023: Validate the full inventory at preparation, authenticate each publishing batch

Date: 2026-09-23. Status: accepted implementation direction; rollout evidence is separate.

## Context

The owner wants all linked teams prepared silently, unchanged model search and offer
availability, and a three-second first-action target. A single JSON artifact rejected
a synthetic13728-offer inventory at461.5MB before saving. Bounded pages solved that
transport limit, but repeating semantic validation over the whole inventory at every
interactive request made even936 offers take17.06s to reach the first30 durable cards.
These are local synthetic results, not production/device timing.

## Decision

Keep SQL-backed private manifests, bounded pages and original diagnostic nodes. Index
all consumed participants before private writes. Freeze the descriptor tree/root
before full semantic validation. Only the trusted sealer can mint a recognized,
versioned semantic attestation after validating that exact root, scope, identities,
counts, order, uniqueness, original proof/evidence/candidate links and expiry.
Install the sealed active pointer atomically under the original live work claim.

Interactive admission checks the attestation and fresh source/model/account inputs,
and scans the complete root-authenticated compact disposition index. It then fully
validates each publishing batch's exact native cards, original evidence and diagnostic
closure, rechecks the original storage slice, commits evidence and checkpoint, and
only then publishes. No all-proof scan precedes the first batch. Missing/unknown
attestation is a miss. Retain explicit full preflight for sealing and diagnostics.

This deliberately changes the corruption contract: a later corrupt page can leave an
earlier independently verified prefix visible. The corrupt batch never becomes
actionable; an error after commitment never appends an unrelated fresh suffix.
Root hashes are integrity bindings within trusted database/store-writer authority,
not protection from an administrator rewriting the entire database.

## Alternatives considered

- Increase whole-artifact bounds: repeats large allocations and risks SQL memory.
- Truncate offers/search budgets: violates the owner instruction and changes model coverage.
- Repeat all-proof preflight on every hit: valid but defeats the first-action objective.
- Trust a caller's `validated` flag or page-local checks alone: cannot establish complete
  cross-page semantic validity and global order/identity invariants.
- External object storage/queue: not required for this bounded SQL implementation;
  does not by itself remove semantic revalidation cost.

## Consequences

Preparation remains silent, not user activity or evidence of acceptance. Account
deletion removes staging, validating, sealed and retired records and children;
exports omit private payloads. Same-token leases recover work without extending
artifact expiry. Cache-off is the operational rollback; pre-v2 binary downgrade
requires a verified purge or deletion-compatible bridge. Native generator and
cumulative published inventory memory remain separate qualification limits.

[Plan and validation requirements](../plans/prepared-trade-inventory/chunked-storage-plan.md)
· [Actual rollout evidence](../plans/prepared-trade-inventory/release.md)
