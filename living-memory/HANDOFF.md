# HANDOFF — Fantasy Trade Finder

> **Purpose:** launch release handoff after the #629/#628 deploy.
> **Read at:** session start. **Write at:** checkpoint/session end.
> Companion files: [CHANGELOG.md](CHANGELOG.md), [NEXT.md](NEXT.md), [TEST_LEDGER.md](TEST_LEDGER.md).

---

## Table of Contents

- [Current State 2026-11-09](#current-state-2026-11-09)
- [Unmerged 2026-11-10: page-first trade search](#unmerged-2026-11-10-page-first-trade-search)

---

## Current State 2026-11-09

**Where I stopped**
- `main` and the live Render deploy are both `b1440b7b` (#629 give-all fix with pipeline 14, #628 iPhone timing tags), deployed 2026-11-10T02:53Z before the Nov 10 freeze. That SHA is the frozen candidate for the Nov 10 check.
- Calibration `outlook-v2-v3-1` was rebuilt once on that revision: 10 ready, 1 started (its 3 answers kept), 5 known provider failures.
- Work moved to a new MacBook with `gh` (mattmurf77), Python 3.12, Node 20 (via `~/.zprofile`) and `eas-cli`. `prototype/p1-reviewed-integration` (`447a9e27`) and `prototype/p1-atomic-ready` (`85a75ddb`) were recovered from zips; they stay offline by decision and are not on GitHub.

**In flight**
- TestFlight 1.22.0 (183), built from `eaf3f6ae` (same code as `b1440b7b`), is in internal beta testing as of 2026-11-10T04:10Z. Physical-iPhone timing runs on it haven't started. `eas` is logged in as mattmurf77.

**Blocked on**
- The 200 ms gate needs build-183 samples from at least 2 physical iPhones, at least 40 per `all-entry` cohort (`qa/instant-trade-acceptance.md`, `--require-physical-iphone --client-build 183`).

**Don't repeat**
- No simulator or Maestro (D-056). Production runs a single worker: a Calibration rebuild takes about 4–5 min per pair and starves admin reads, so run them off-peak.

## Unmerged 2026-11-10: page-first trade search

- **Where:** branch `feat/offer-learnings`, PR #641 (contains PR #638). Worktree `.claude/worktrees/offer-learnings`. Every new flag is off in it.
- **What:** the fast deck (ADR-028, D-215, D-216) and the offer-learnings programme (ADR-029, D-217 to D-226; specs in `docs/plans/offer-learnings/plan.md`).
- **The operator's instruction (2026-11-10, then away):** finish the code, merge, ship a TestFlight build and turn it on. Plan: merge dark, confirm the deploy, turn features on in a second change, build 1.23.0, pre-generate the revision-4 Calibration round.
- **Stays off until the operator acts:** `trade.sleeper_offer_import` (the Terms and Privacy wording is drafted, not published; revised-offer cards have nothing to show until it is on); revision 4's selector and `trade.partner_activity` (graded first).
- **Owed:** models-eng review of the pipeline bump (15 → 21); the TestFlight checklists in each scope block.
- **Local only, never commit:** `data/sleeper-export/` and `data/prod-requests/` in the main checkout.
- **Builder worktrees** (`.claude/worktrees/agent-*`) and their branches are to be swept through `docs/recovery/` once their content is verified on `main`.

