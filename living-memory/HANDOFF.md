# HANDOFF — Fantasy Trade Finder

> **Purpose:** launch release handoff after the #629/#628 deploy.
> **Read at:** session start. **Write at:** checkpoint/session end.
> Companion files: [CHANGELOG.md](CHANGELOG.md), [NEXT.md](NEXT.md), [TEST_LEDGER.md](TEST_LEDGER.md).

---

## Table of Contents

- [Current State 2026-11-09](#current-state-2026-11-09)
- [Shipped 2026-11-10: offer learnings and fast deck, on in production](#shipped-2026-11-10-offer-learnings-and-fast-deck-on-in-production)

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

## Shipped 2026-11-10: offer learnings and fast deck, on in production

**Where I stopped**
- This release is `13865d73` (#641 dark at `0baf6360`, then #643). `main` moved on to `38be9052` the same hour (#642, another session turning on `trades.roster_setup`); build 184 was cut from `13865d73` and already contains that feature's app code. On in production: `trade.fast_deck`, `trade.fit_first_copy`, `trade.pass_reason_cadence`, `trade.outcome_tracking`, `trade.next_move`, `grading.revision4_round`, `trade.sleeper_offer_import`. The Current State section above predates this.
- The operator approved the Terms and Privacy wording; it is published (effective date November 10, 2026, consent version `offer-import-1`).
- iOS 1.22.0 (184), EAS build `55914797-24b5-4035-a5cf-c894facbad57` from `13865d73`, auto-submit `f439db03-04e9-48b9-ae3f-0a8a05174932`. Build and submission both FINISHED (uploaded 05:35Z); Apple processing and tester availability not checked.
- Revision 4 Calibration round `outlook-v2-v4-1` queued for all 16 connected pairs at 05:29Z. Result: 11 ready, 5 provider failures; 150 of 200 selected cards are shared between revision 2 and revision 4.

**In flight**
- Nothing in code. [Release record](../docs/business/ops/2026-11-10-offer-learnings.md); next steps in [NEXT](NEXT.md).

**Blocked on**
- The operator: TestFlight checklists on 184; models-eng review of pipeline 15 → 21. The Sleeper read's reach is settled (D-227, 2026-11-11: app-sent trades are followed without the switch).

**Don't repeat**
- A flag turned on in `config/features.json` breaks tests that read the shipped config and assume it is off. Run the full suite on the turn-on commit, not only on the dark one.
- `web/privacy.html` has verbatim legal checks (`qa/web/check_web_structure.py`, `POL-*`); a new bullet inside a checked passage fails them.
- CI's backend job takes about 40 minutes on this tree.
- Off on purpose: revision 4's selector and `trade.partner_activity` (graded first); `trade.fast_deck_shadow`.
- Local only, never commit: `data/sleeper-export/` and `data/prod-requests/` in the main checkout.
- Left for the next sweep: worktree `.claude/worktrees/offer-import-terms` (branches `docs/offer-learnings-release`, PR #644, and `feat/sleeper-read-app-sent`, the D-227 change). Every other worktree and branch of this programme is in [the ledger](../docs/recovery/2026-11-10-offer-learnings.md).
