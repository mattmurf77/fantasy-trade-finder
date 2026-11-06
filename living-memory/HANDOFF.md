# HANDOFF — Fantasy Trade Finder

> **Purpose:** current authorized launch/performance work; GitHub is authoritative.
> **Read at:** session start. **Write at:** checkpoint/session end.

## Table of Contents
- [Current State — 2026-11-06](#current-state--2026-11-06)

## Current State — 2026-11-06

User authorized all GitHub actions and autonomous launch work. Current task:
actual Find a Trade tap-to-actionable-card <=200 ms including immediate
league/preferences/pin changes, with no quality downgrade. Requirement remains
OPEN; no synthetic/prewarmed-only evidence may certify it.

PR604 `fix/instant-trade-scopes`, recovered from `d79592f3` in
`/private/tmp/fleeced-instant-trades`. Main last verified `60d861dd`. Native
recovery+early probe+input save/paging fences+strict filters+prepared durable
prefix and immutable scalar projection changes committed. See feature scope
and TEST_LEDGER for evidence and known cold-path limitations. Latest code
commit before this checkpoint: `ca839ec1`; mobile CI correction `f0123982`.
Next: push final checkpoint, verify all4 exact-head CI jobs, merge only green
reviewed code. Render auto-deploy then TestFlight candidate requires a NEW
mobile build; EAS173 finished from lost prior `eb33443` and lacks current fixes.
No new candidate submitted, no global preparation enabled.

Keep #456 held until November18/public installability; no public App Store
submission/release without go/no-go. Calibration public, KTC blend0. User
declined DB restore-copy exercise. No simulator/Maestro substitute for native
frame evidence. No purchases/Pro grants/identity impersonation.

Production read-only checks November6: Render DB10GBplan,38%diskused,~6.5GB
free on reported filesystem; autoscalingoff. Biggest tables deck_impressions
~2.95GB and deck_diagnostic_snapshots~669MB. Live paywall flagon, entitlement
enforcement flagoff, guided onboardingoff. Signup and subscription invitation
are built but automatic paid-access invitation requires enforcement; do not
activate it merely because user asked whether it exists.
