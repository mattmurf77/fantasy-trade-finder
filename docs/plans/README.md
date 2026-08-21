# `docs/plans/` — initiative index

Working docs for multi-step initiatives: plans, PRDs, HLDs/LLDs, feature scopes, research
memos, reconciliation logs. **This is not a record of what shipped** — a plan folder can be
years-dead or fully live and the files look identical. The status columns below are the only
way to tell; keep them current.

Two artifact shapes live here:

1. **Flat plans** (`<slug>.md`) — one document, usually one session. See [Flat plans](#flat-plans).
2. **Thread folders** (`<slug>/`) — a doc set for an initiative. See [Thread folders](#thread-folders).

For **what changed and when**, read [`living-memory/CHANGELOG.md`](../../living-memory/CHANGELOG.md).
For **what's next**, [`living-memory/NEXT.md`](../../living-memory/NEXT.md). For the **decisions**
cited below, [`living-memory/DECISIONS.md`](../../living-memory/DECISIONS.md).
Per-feedback-item fixes do **not** live here — they live in [`../feedback/items/`](../feedback/items/).

## Status legend

| Status | Means |
|---|---|
| **shipped** | The described work is on `main` and reachable by users (flag ON or unflagged) |
| **built dark** | Built and merged, but gated off — flag `false` |
| **partly shipped** | Some items in the doc set shipped, others were never built |
| **active** | Current initiative, design settled or in flight, not built |
| **not built** | Written, never implemented; still the intended design if picked up |
| **superseded** | A later doc or decision replaced it; read for history only |
| **abandoned** | Started and left; no one is coming back to it as written |
| **reference** | Research/evidence capture, never intended to "ship" |

Dates in the tables are the date the status became true (or the doc's own date for
reference material), not the file's last-edit date.

## Thread folders

| Folder | Files | Status | What it is / evidence |
|---|---|---|---|
| [counterparty-breaker/](counterparty-breaker/) | 12+ | **active** · 2026-08-21 | Adversarial pass that evaluates every trade suggestion from the OTHER manager's seat and surfaces their strongest objection (predicted `trade_pass_reasons` code + evidence + hesitation line). Full suite converged via dual-agent review: [PLAN](counterparty-breaker/PLAN.md) → [HLD](counterparty-breaker/HLD.md) → [LLD](counterparty-breaker/LLD.md) → [PRD](counterparty-breaker/PRD.md), [reconciliation-log](counterparty-breaker/reconciliation-log.md), drafts kept. Three-way reconciled with the Receipts + negative-results-memory plans (shared taxonomy v1.1.1 on `plan/receipts`, producer column). v1 = stamp + narrative only, zero ordering effect, both flags dark; 20-item operator register in PRD §9. Build authorized post-PRD by operator instruction — in progress on `claude/counterparty-breaker-plan`. |
| [three-model-bakeoff/](three-model-bakeoff/) | 4 | **partly shipped** · 2026-08-18 | Three-model trade-engine bake-off ([PLAN.md](three-model-bakeoff/PLAN.md)), plus the board-override-pin work the [2026-08-18 valuation audit](../reviews/2026-08-18-valuation-age-audit.md) forced into Phase 0. [scope-phase0.md](three-model-bakeoff/scope-phase0.md) shipped (`e8ae476`, D-069/D-070); [scope-phase2.md](three-model-bakeoff/scope-phase2.md) (D-075, arm A pinned) is branch-only; [scope-tier-bounded.md](three-model-bakeoff/scope-tier-bounded.md) (D-076) supersedes half of Phase 0 — a pin now confines a player to a tier instead of freezing him — and is **built, not shipped**, on `feat/tier-bounded-pins`. |
| [analytics-platform/](analytics-platform/) | 7 | **partly shipped** · 2026-07-18 | First-party analytics + experimentation. P0–P2 built (`analytics.ingest`, `experiments.engine` ON; ADR-007). P3/P4 unbuilt. Has its own [README](analytics-platform/README.md) with per-phase state. |
| [trade-relevance-engine/](trade-relevance-engine/) | 8 | **active** · 2026-08-14 | Make trade suggestions interaction-driven the way X's For You feed is — audit FTF's suggestion pipeline against X's open-sourced algorithm and enhance it. Reference: [`reference/x-algorithm/`](../../reference/x-algorithm/README.md). Research corpus: [`../research/matchmaking/`](../research/matchmaking/README.md). Has its own [README](trade-relevance-engine/README.md). |
| [audit-p0-remediation/](audit-p0-remediation/) | 29 | **shipped** · 2026-08-11 | The nine launch blockers from the [2026-08-09 mobile UX audit](../business/product/2026-08-09-mobile-ux-audit/). Eight resolved on `p0-remediation-2026-08-10`; P0-4 withdrawn by the operator. Sweep: [`../recovery/2026-08-11-p0-remediation-sweep.md`](../recovery/2026-08-11-p0-remediation-sweep.md). Deferrals live in `NEXT.md` § 2026-08-11. Has its own [README](audit-p0-remediation/README.md). |
| [audit-p1-remediation/](audit-p1-remediation/) | 28 | **shipped** · 2026-08-12 | P1 tier of the same audit — tier-board exposure closed, share loop wired, invite promoted, anchor unlock fixed. Operator rulings in [`DECISIONS-p1.md`](audit-p1-remediation/DECISIONS-p1.md) bind any later build. Has its own [README](audit-p1-remediation/README.md). |
| [competitor-top20/](competitor-top20/) | 21 | **partly shipped** · 2026-07 | 20 per-feature deep dives (PRD+HLD+LLD each) off the 92-item [competitor backlog](competitor-feature-backlog-2026-06-11.md). Several shipped (`trade.outlook_infer`, `trade.preference_lists`, `trade.crown_asset`, `trade.outlook_seed`); several never built (`tiers.community_diff`, `league.power_rankings` are still `false`). Per-file state is **not** tracked — check the flag before assuming. |
| [connected-rankings/](connected-rankings/) | 7 | **active, not built** · 2026-08-15 | Board provenance, zero-credential source connectors, assisted CSV import from DLF/Dynasty Nerds. Plan is dual-agent final; scope gated on operator questions. See [D-058]. Untracked in git as of 2026-08-18. |
| [decline-reason-capture/](decline-reason-capture/) | 1 | **active, not built** · 2026-08-17 | Operator-approved build spec for a two-layer trade-decline reason capture. Prototype: `mockups/decline-reason-capture/07-two-step-diagnostic.html`. Untracked in git. |
| [draft-extensions/](draft-extensions/) | 22 | **shipped** · 2026-08-08 | Rookie-rank bridge, ESPN manual draft tracking, mock drafts. `draft.mock`, `draft.tab`, `draft.manual_picks`, `picks.assign` all ON. Includes the mock-draft calibration sweeps. Has its own [README](draft-extensions/README.md). |
| [dynasty-year-in-review/](dynasty-year-in-review/) | 5 | **active, not built** · 2026-08-13 | "Wrapped" (#46). Design reconciled; the time-critical part is roster-history *capture*, not the recap. Owner doc is [`../business/product/2026-08-13-dynasty-year-in-review-plan.md`](../business/product/2026-08-13-dynasty-year-in-review-plan.md). Has its own [README](dynasty-year-in-review/README.md). Untracked in git. |
| [espn-connect-webview/](espn-connect-webview/) | 1 | **shipped** · 2026-08-08 | Feature scope for ESPN in-app WebView cookie capture. `espn.webview_capture` ON. |
| [feedback-backend-sync/](feedback-backend-sync/) | 3 | **abandoned** · 2026-06-07 | Round 01 was never seeded; `status.md` has said "discovery / not yet seeded" since 2026-06-07. |
| [feedback-batch-2/](feedback-batch-2/) | 10 | **shipped** · 2026-06-08 | Feedback ids #26–#41, seven features, PRs #77–#83. Pre-dates the `items/<id>-<slug>/` convention. |
| [feedback-batch-3/](feedback-batch-3/) | 12 | **status unclear** · 2026-06-11 | Feedback ids #49–#58 (v1.2.0 first-hour testing). `plan.md` records the bugs as built on a branch (`d161b80`) "awaiting on-device QA" and never states a merge; no changelog entry closes it. Pre-dates the item-folder convention. |
| [feedback-batch-4/](feedback-batch-4/) | 5 | **status unclear** · 2026-06-19 | Feedback ids #59, #61–#63 off `origin/trade-engine-v2`. #60 deferred by the operator. No merge is recorded in the folder or the changelog. Last of the batch folders. |
| [mobile-feature-parity/](mobile-feature-parity/) | 4 | **abandoned** · 2026-06-07 | Same fate as `feedback-backend-sync/` — discovery phase, round 01 never seeded. |
| [mobile-testing/](mobile-testing/) | 11 | **superseded** · 2026-08-15 | The Maestro/simulator testing system (plan, PRD, HLD, LLD, 201 test cases). **Retired entirely by [D-056]** — no flow authoring, extension, or execution, in any pipeline. Kept as history; do not budget work against it. |
| [monetization/](monetization/) | 17 | **not built** · 2026-07-19 | PRD/HLD/LLD for five monetization plans + the shared platform foundation. No `monetize.*` flag exists in `config/features.json`; nothing was implemented. Read [`00-platform-foundation.md`](monetization/00-platform-foundation.md) first. Has its own [README](monetization/README.md). |
| [notif-inbox-growth/](notif-inbox-growth/) | 2 | **status unclear** · 2026-08-13 | Notification inbox as a growth surface, phase 1. `CHANGELOG.md` records it as shipped 2026-08-13; `NEXT.md` and `HANDOFF.md` still describe `feat/notif-inbox-growth` as **unmerged**. Confirm against `origin/main` before building on it. |
| [onboarding-conversion/](onboarding-conversion/) | 5 | **built dark** · 2026-08-11 | Value-first first launch (v2.1, incl. the guided layer). `onboarding.v2` is ON as the master switch but **all seven sub-flags are `false`**, so no redesigned screen is live. |
| [perf-optimization/](perf-optimization/) | 11 | **shipped** · 2026-06-07 | Wave 2 complete — 8 items, PRs #67–#70, ADR-001. Wave 3 and INIT-08-backend were never started. The only folder that fully used the round-based protocol below. |
| [rookie-draft/](rookie-draft/) | 14 | **shipped** · 2026-08-06 | Rookie rankings + live draft support. `ranks.rookie_subset`, `draft.room`, `draft.live_poll`, `picks.slot_values` all ON; ADR-009, ADR-010. Has its own [README](rookie-draft/README.md). |
| [settings-ia-hub/](settings-ia-hub/) | 3 | **active, building** · 2026-08-19 | Reorganize mobile Settings from one ~25-control modal sheet into a hub page + five second-level pages, and change the presentation from `presentation: 'modal'` to a pushed page. Flag `account.settings_hub`, default off; retires `account.settings_v2` in phase 4. Plan reviewed against **live prod flag state** 2026-08-18, not an on-device pass. Mockup: `mockups/settings-ia-hub/`. |
| [negative-results-memory/](negative-results-memory/) | 15 | **BUILT dark — not merged, nothing lit** · 2026-08-22 | Per-league memory of reasoned rejections as a SOFT generation-time prior (M1) + feeding gen_v2's unfed `acceptance_prior` (M2). Full suite ([PLAN](negative-results-memory/PLAN.md) → [PRD](negative-results-memory/PRD.md) → [HLD](negative-results-memory/HLD.md) → [LLD](negative-results-memory/LLD.md), reconciliation-log, drafts kept) then **built in four waves** on `claude/vigilant-spence-8583f5` — the operator's three §6 rulings (2026-08-22) opened the gate. Decision record: [ADR-015](../adr/adr-015-negmem-soft-prior-not-fourth-filter.md) / [D-147](../../living-memory/DECISIONS.md). Flag `trade.negmem` **false** and `config/negmem_leagues.json` **empty** — the ON-condition is BOTH, so nothing is lit and no runtime evidence exists; the [TestFlight checklist](negative-results-memory/testflight-checklist.md) is UNRUN. |
| [tiktok-discovery/](tiktok-discovery/) | 16 | **partly shipped** · 2026-08 | Ten PRDs for a TikTok-style trade deck. F1–F5, F7, F9, F10 shipped (`deck.signal_v2`, `deck.thompson_v2`, `deck.fatigue`, `deck.session_rerank`, `deck.taste_vectors`, `deck.exploration`, `deck.first_session`, `deck.replenishment` all ON). F6 not built (`deck.value_model` `false`); F8 is operator tooling. Has its own [README](tiktok-discovery/README.md). |
| [_templates/](_templates/) | 4 | **reference** | Templates for the round-based protocol. Only `perf-optimization/` ever ran it end to end — see [Conventions](#conventions). |

## Flat plans

### Active

| Doc | Status | Notes |
|---|---|---|
| [device-side-platform-auth-prd-2026-08-12.md](device-side-platform-auth-prd-2026-08-12.md) | **active** | Device-held platform credentials. Dual-agent final, 4 rounds. Operator defaults ratified as [D-047]; ADR-011 on `main`. |
| [device-side-platform-auth-hld-decisions-2026-08-13.md](device-side-platform-auth-hld-decisions-2026-08-13.md) | **active** | The HLD decision set for the above. Binding on `connected-rankings/`, which conforms rather than re-litigates. |
| [pending-trades-inbox-plan-2026-08-12.md](pending-trades-inbox-plan-2026-08-12.md) | **not built** | Cross-platform pending-offer inbox (Sleeper/ESPN/MFL) as a third Matches tab. No flag exists. |

### Shipped (kept for the reasoning trail)

| Doc | Shipped | Evidence |
|---|---|---|
| [account-auth-plan-2026-07-11.md](account-auth-plan-2026-07-11.md) | 2026-07-12 | `auth.accounts` ON; ADR-006. |
| [espn-league-linking-plan-2026-07-11.md](espn-league-linking-plan-2026-07-11.md) | 2026-07-12 | `espn.link` ON. Its deferred Phase 1b became [espn-connect-webview/](espn-connect-webview/). |
| [manual-trade-calculator-plan.md](manual-trade-calculator-plan.md) | 2026-07-09 | Modes A and B both implemented — status banners are inline at the top of the doc. |
| [trade-finder-targeting.md](trade-finder-targeting.md) | — | `trade.finder_targeting` ON. |
| [trios-tier-calibration-plan-2026-07-08.md](trios-tier-calibration-plan-2026-07-08.md) | 2026-07-10 | Shipped with the FB-#97 variety fix; addenda are inline. Trio-driven Lever B remains design-only. |
| [trade-engine-tier1-fixes.md](trade-engine-tier1-fixes.md) · [tier2-models](trade-engine-tier2-models.md) · [tier3-rebuild](trade-engine-tier3-rebuild.md) | 2026-06 | Superseded by what actually landed — read [ADR-002](../adr/adr-002-trade-engine-v2-v3-rebuild.md). `trade_engine.v2` + `v3` ON. |
| [auth-multiplatform-plan-2026-06-11.md](auth-multiplatform-plan-2026-06-11.md) | partly | Part C (Sleeper write) shipped as `trade.send_in_sleeper`. Other parts folded into the ESPN/MFL plans. |

### Reference / research (never meant to ship)

| Doc | What it captures |
|---|---|
| [sleeper-pending-trades-feasibility-2026-08-12.md](sleeper-pending-trades-feasibility-2026-08-12.md) | Sleeper pending-offer feasibility — the memo feature #11 was gated on |
| [sleeper-ios-reachability-probe-result-2026-08-12.md](sleeper-ios-reachability-probe-result-2026-08-12.md) | On-device Sleeper reachability probe, PASS 4/4 |
| [espn-send-live-capture-2026-08-11.md](espn-send-live-capture-2026-08-11.md) | Live ESPN trade-write probes that reversed the standing NO-GO |
| [send-in-espn-research-2026-08-11.md](send-in-espn-research-2026-08-11.md) · [send-in-mfl-research-2026-08-11.md](send-in-mfl-research-2026-08-11.md) | Per-platform trade-lifecycle research |
| [sleeper-write-capture-runbook.md](sleeper-write-capture-runbook.md) | Human-run capture runbook for Sleeper's undocumented login/trade endpoints |
| [multi-platform-linking-plan-2026-07-17.md](multi-platform-linking-plan-2026-07-17.md) | MFL/Fleaflicker/Yahoo/FFPC linking decision doc. MFL shipped (`mfl.link` ON); `fleaflicker.link` is still `false` |
| [market-data-readiness.md](market-data-readiness.md) | Market-driven rankings + risers/fallers audit (2026-07-26) |
| [trade-logic-interview-2026-07-17.md](trade-logic-interview-2026-07-17.md) | The operator's trade philosophy, transcribed — the source for roster-fit and lane rules |
| [competitor-inspired-features-2026-06-10.md](competitor-inspired-features-2026-06-10.md) · [competitor-feature-backlog-2026-06-11.md](competitor-feature-backlog-2026-06-11.md) | The 92-item ranked backlog that [competitor-top20/](competitor-top20/) drills into |

### Historical

| Doc | Why it's here |
|---|---|
| [launch-qa-plan-2026-06-11.md](launch-qa-plan-2026-06-11.md) + [phase1-report](launch-qa-phase1-report.md) + `launch-qa-phase*-findings.json` | The 2026-06 pre-launch QA sweep. Findings acted on; the plan is not a live process. |
| [claude-xcode-testing-plan-2026-07-09.md](claude-xcode-testing-plan-2026-07-09.md) | Superseded by [mobile-testing/](mobile-testing/), which is itself retired by [D-056]. |
| [loop-hld.md](loop-hld.md) · [loop-lld.md](loop-lld.md) · [loop-prd.md](loop-prd.md) | **Status unclear.** The five FTF self-training loops (2026-07-03). No flag or changelog entry names them; the spec source is outside the repo. Verify before treating any of it as built. |

## Conventions

**Adding a doc.** Flat file for one-session work. Promote to a folder when the work spans
sessions, spans agents, or needs iteration. When you make a folder, add its row to the table
above **in the same session** — an undocumented folder is indistinguishable from a dead one
within a week.

**Feature scopes.** Any change touching user-visible behavior, data collection, schema, or API
copies [`../templates/feature-scope.md`](../templates/feature-scope.md) into the feature's home —
that's `<thread-folder>/scope.md` here, or the feedback item's folder. Recent folders
(`espn-connect-webview/`, `notif-inbox-growth/`, `audit-p*-remediation/`) follow it; older ones
pre-date the rule.

**Naming, as actually practiced.** There is no single enforced file layout. What recurs:
`plan.md` (the brief), `scope.md` (the feature-scope block), `prd.md`, `hld.md`/`lld.md`,
`reconciliation-log.md` (dual-agent review rounds), `build-*.md` (per-wave build briefs),
`research/` (sourced evidence). Batch folders suffix per-item (`prd-p0-1.md`, `LLD-p1-3.md`).
Match the neighbours in the folder you're adding to.

**The round-based protocol is legacy.** `_templates/` and [CLAUDE.md](CLAUDE.md) describe a
`status.md` / `conversation.md` / `round-NN-*.md` handoff protocol
([`../agent-collab-protocol.md`](../agent-collab-protocol.md)). Only `perf-optimization/` ran it
to completion; `feedback-backend-sync/` and `mobile-feature-parity/` stalled at round 01 and
never resumed. Everything built since 2026-07 uses the dual-agent plan/PRD/HLD/LLD +
reconciliation-log shape instead. Those files are **tracked in git**, not gitignored — despite
what older docs claimed; `.gitignore` has never had a rule for them.

**Closing a thread.** Update this table's status row, then promote durable changes per the
trigger table in [`../CLAUDE.md`](../CLAUDE.md) (ADRs, data-dictionary, api-reference, glossary,
runbook, cross-client-invariants) and write the dated entry in
[`living-memory/CHANGELOG.md`](../../living-memory/CHANGELOG.md). Folders are never deleted.

[D-047]: ../../living-memory/DECISIONS.md
[D-056]: ../../living-memory/DECISIONS.md
[D-058]: ../../living-memory/DECISIONS.md
