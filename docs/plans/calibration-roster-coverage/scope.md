# Calibration complete roster coverage

Date: 2026-11-06. Entry: all-connected-league preparation exposed deep-bench holdings outside the ranked pool. Parent authorized this isolated correction before provider expansion.

## Analytics and schema
Existing grading sources/proofs/report cover the outcome. No new events, tables, flags or routes. No organic activity or provider writes. Existing prepare/round switches provide rollback. No mobile changes or new binary.

## Input and architecture contract
`calibration_roster_coverage.add_unranked_occupancy` extends only the strict calibration safety context, never the owner generator/player pool. A held player absent from that pool requires known QB/RB/WR/TE metadata; inconsistent player identity or unknown position stays unresolved. Fresh metadata supplies availability; only active=true and no unavailable injury status count as available. Reserve/taxi remain attached to their actual team. Unknown-price numeric zero is an internal arithmetic sentinel, explicitly market_value=null, noncandidate and nonusable in private evidence. It cannot satisfy usable starter or replacement-depth checks. Capacity includes occupied active slots. Qualified roster diagnostics label sums priced-assets-only. Public catalog exposes null value for these never-traded holdings.

The input fingerprint includes every consumed metadata fact: fantasy_positions, position, player_id, active and injury_status. Capture retains the exact raw held IDs for both consistency checks and later currentness, including newly observed holdings absent from persisted members and the pool. New code invalidates unexposed snapshots; reprepare after deploy. Exposed snapshots retain original evidence. Unknown metadata and unsupported K/DST/IDP lineups still fail. Safety means the existing declared lineup/depth/capacity checks, not exhaustive platform transaction legality.

## Evidence
Unit and actual two-engine tests verify restored complete-roster coverage, unchanged native inventory, no unpriced trade legs/value benefits, full proof matching, capacity/IR handling, unknown metadata refusal and known-change invalidation. Existing lifecycle/privacy tests remain required. No simulator/Maestro. Operator checklist: after CI/deploy reprepare blocked unexposed canaries, inspect aggregate errors/counts and one frozen blind card; do not promise all-ready for unsupported leagues.

## Documentation
Architecture and round contract updated; LLD/HLD calibration notes updated. API wire contract, shared client enums, glossary and data dictionary unchanged. Existing ADR027 scope retained; private proof now distinguishes unknown-price occupancy from ranked market evidence.

## Ship gates
Exact-head CI plus independent output review and TEST_LEDGER. No express waiver. Parent owns PR/deploy/preparation. Provider expansion is separate follow-up.
