# ADR-021: Store repeated deck diagnostics once and expire debug detail

Date: 2026-09-15
Status: Accepted

## Context

The 1 GB production database was suspended after reaching 98.3% disk use.
Impressions account for most storage: recent jobs write about 910 cards each,
with repeated request/configuration/roster/generation context. Valuations,
explicit outcomes and training denominators must remain trustworthy.

## Decision

Preserve all cards and core evidence. Normalize four debug JSON roots into
immutable nodes, scoped to user/job; recursively share repeated subtrees of
at least 1 KiB. Keep diagnostic detail 14 days by default. Explicit diagnostic
reads reconstruct exactly while present and clearly mark expired nodes.
Atomic, bounded writes and private export/deletion cover the new table.

## Alternatives considered

Capping generated cards changes accepted product behavior. Sampling impressions
would alter training denominators. Deleting old impression rows risks losing
receipt/outcome links and barely addresses recent growth. Plain vacuum cannot
remove live repeated payloads. Merely increasing disk defers recurring growth.

## Consequences

Raw diagnostic SQL must follow references; offline inspection can use the
resolver or exported snapshot table. Detailed debugging beyond retention needs
a recovery archive; core valuation/outcome evidence remains durable. The disk
increase restored service, but data transformation and physical reclamation
are separate, verified maintenance operations.
