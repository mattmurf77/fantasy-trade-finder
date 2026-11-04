# Launch integration: roster moves, tips and share cards

Local integration candidate, 2026-11-04. This records code integration and
synthetic validation, not a deployment or activation decision.

## Included ancestry and foundations

The batch preserves the original heads of #379 → #528 → #509 → #579, #578,
#575 → #583 plus #576, and #564 → #581 plus #573. It also retains reviewed
privacy/Shop parent `59daef9c` (#592) and paywall parent `7bb7ff86` (#590).
Both foundation PRs must land before this child is retargeted to main.
The separately owned #565 terms/privacy documentation batch is not duplicated.

## Integration decisions

- Free-agent reads, roster-move submission and GET/DELETE consent are FREE in
  the global paywall table. Their own authentication, verification, consent,
  credential and kill-switch checks remain in place.
- The share snapshot columns and deletion-scrub schema additions coexist.
  Neutral PK chips cover both concrete owned picks and generic picks, while
  preserving the stored snapshot and side orientation.
- Founder/club/trial paywall configuration coexists with the tip configuration:
  tips are served only to verified non-demo iOS sessions with the exact live
  tip knob value 1. The seeded knob stays 0. Source feature values are unchanged
  from main `af57e59c`, apart from the new `sleeper.send_add_drop: false` key.
- D1 client exposure and server consent-ledger event classifications coexist
  with NON_INTENT entitlement grants. No success event is reclassified.
- Both evidence histories are retained when ledger/docs insertions conflict.

## Validation and activation boundary

Targeted integrated backend run: **1100 passed, 3 skipped**. It covers consent,
capability, the simulated provider move route, paywall configuration/gate and
route completeness, immutable share snapshots/labels/links/tokens, event
classification, account deletion, deletion scrub and Shop sends. Two skips
were the optional Postgres move races; both subsequently passed against a
disposable socket-only PostgreSQL cluster with synthetic data and an injected
fake provider (**2 passed**). The remaining skip is a preexisting #389 generic
pick Shop guard absent from this base.

Executed mobile structural/behavior guards pass: external links, Sleeper
handoff and event contract, D1 (**115**), tip identity/config/purchase simulation
(**23**), global paywall gate (**109**), Shop send (**33**), trade text and
share-token fallback (**19**). TypeScript and Zustand were loaded read-only
from the existing dependency worktree; an external preload redirects the D1
script's absolute Zustand lookup, without changing any test assertions.
`git diff af57e59c --check` passes. No full local suite, simulator or device run.

D1 remains dark pending captured provider request/response shapes and the
existing consent/device activation gates; all provider tests are synthetic.
Tips remain dark pending StoreKit/RevenueCat product and verified-identity
activation proof. No credentials, live platform writes, purchases, captures,
production settings or source feature flags were changed. Full GitHub CI and
review remain merge gates.
