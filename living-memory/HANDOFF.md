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

- **Where:** branch `feat/trade-engine-rearch` on top of `main`. Worktree `.claude/worktrees/trade-engine-rearch`.
- **What:** `backend/trade_first_page.py` (ADR-028, D-215), the fast deck `backend/trade_fast_deck.py` with its hook in `_run_trade_job` (D-216, flags `trade.fast_deck` and `trade.fast_deck_shadow`, both off), eval tooling, and `docs/plans/realtime-trade-engine/`.
- **Do not merge without the operator's word.** The backend changed (deck pipeline 15 → 16), so merging deploys to Render, rebuilds stored first pages once, replaces the frozen `b1440b7b` candidate the Nov 10 check and the iPhone timing runs are tied to, and is a MOD-M1 re-run trigger. models-eng review of the bump is owed.
- **Done:** code review of the search and its revision-2 exactness; 172 + 27 + 3 + 16 targeted tests; replay of 247 recorded production requests (all match).
- **Next:** after merge, shadow for a day, then the serve flag and the TestFlight checklist in the scope block; then NEXT.md's 2026-11-10 section.
- **Numbering:** roster-first setup (#637) and manager profiles (#635) merged first and took D-212 to D-214 and pipeline 15, so this branch is D-215 (page-first search), D-216 (fast deck) and pipeline 16.
- **Local only, never commit:** `data/sleeper-export/` (the operator's Sleeper inbox export and offer-analysis scripts) and `data/prod-requests/` (recorded production requests and replay results), both in the main checkout.
- **Related sessions, separate branches:** roster-first setup (`feat/roster-setup-backend`, `feat/roster-setup-mobile`) and manager profiles (PR #635). Neither is reviewed here.

