# ADR-008 — Teardown Remediation Wave (2026-07)

**Status:** Accepted (in flight on branch `teardown-remediation`)
**Date:** 2026-07-19
**Initiative:** Remediation of the 2026-07 full-app teardown. Audit source: `app-teardown-review/` at the project root — **gitignored** (two independent auditor agents per section, nine sections + master report + per-section PRDs). Because the source is untracked, this ADR is the durable record of what the wave decided; the flag inventory lives in [config-reference.md → App-teardown remediation](../config-reference.md).

---

## Context

A methodology-based teardown (navigation/IA, visual & layout, touch, instructional design, notifications, account/settings, cohesion/must-haves/performance, accessibility, trust & monetization) graded every surface of the app against consumer-app platform norms. Composite verdict: methodology-literate app, world-class pockets (deferred signup, deletion flow, instructional honesty), systemic platform-layer gaps (Dynamic Type, Reduce Motion, deep-link coverage, tap routing, data export, session durability). Each section produced PRDs; a multi-agent build wave implements them on `teardown-remediation`.

Two properties of the remediation demanded a recorded decision: how to ship ~30 behavior changes safely into a live TestFlight product, and which auditor findings we deliberately decline.

## Decision

### 1. Flag everything dark

Every behavioral change ships behind its own feature flag, **all default false**, registered in `config/features.json` under `_comment_teardown` (30 flags: `ux.*`, `a11y.*`, `visual.chalkline_cleanup`, `notif.*`, `growth.share_landing`/`growth.rating_prompt`, `account.*`, `profiles.user_toggle`, `auth.persistent_sessions`, `league.rookie_board_entry`). Rollout is operator-paced, flag-by-flag, with per-flag kill switches — the same posture as the onboarding and monetization waves.

Deliberate exceptions, shipped **unflagged**:
- the league-preferences authz fix (security holes don't get a "keep the hole" switch),
- doc/legal-copy corrections (a wrong document has no rollback value),
- inert accessibility annotations — labels, roles, traits — which change nothing for non-AT users.

The flags are subject to the ship-by / kill-by quarterly review convention (config-reference; 07/prd-04): every flag dark ≥90 days gets a scheduled canary or a deletion decision.

### 2. Three deviations from the audited methodology, accepted

| Deviation | Auditor position | Why we accept it |
|---|---|---|
| **Dark-only appearance — no light mode** | Accept as scoped deviation via ADR, record the tradeoff (S2 A-07 = B-05) | The Chalkline language (ADR-004/005) is designed dark-first and is coherent; a light theme doubles every token decision and QA surface for a solo-operator app pre-PMF. Tradeoffs owned: sunlight legibility, and the Accessibility Nutrition Label declares "Dark Interface" only. Revisit only with real user demand — effort is L. |
| **Custom Chalkline icon set in lieu of SF Symbols** | "Partial — legitimate under a custom language" (both S2 auditors) | The stroke set is deliberate, one spec, consistently applied with weight/size rules (`Icon.tsx`), emoji-free. HIG permits custom symbol languages when applied consistently; brand distinctiveness on the tab bar and boards outweighs SF familiarity. Rider: icons still need Dynamic Type scaling behavior under `a11y.text_scaling`. |
| **Non-native settings list styling** | Methodology default is native inset-grouped list conventions | Settings uses Chalkline card/list styling like every other surface. One design language wholesale (the methodology's own Part X §10 rule) beats a lone native-styled screen; the *substance* of the settings norms — grouping, instant apply, destructive placement — ships via `account.settings_v2` instead. |

### 3. Two explicit deferrals (not rejections)

| Deferral | Trigger to revisit |
|---|---|
| **Widgets / App Intents** (07/prd-03 — the system-integration beachhead) | Requires leaving the Expo-managed workflow (prebuild/dev-client, widget extension target, App Group). Deferred pending the **Expo prebuild decision** — a build-infrastructure choice with its own blast radius that should not ride a remediation wave. The PRD stands as written; nothing else in the wave blocks on it. |
| **Ranking-method usage thresholds** (07/prd-04 item 3 — bury <5%-usage methods into "Advanced") | Kill criteria need usage data read honestly. Deferred pending **analytics review** of ranking-session share per method (the events already collect it). Acting before the readout would bury methods on intuition — the exact antipattern the lifecycle-hygiene PRD exists to stop. |

## Alternatives considered

- **Ship un-flagged, section by section:** rejected — 30 concurrent behavior changes with one rollback unit (a release) on a live TestFlight cohort; the project's existing flag discipline exists precisely for this.
- **One master `teardown.v2` flag** (onboarding-wave pattern): rejected — the wave spans nine unrelated subsystems with independent risk profiles; a master switch couples a notification-honesty fix to a drag-threshold tweak. Per-behavior flags cost little (registry + docs) and the quarterly review bounds their lifetime.
- **Track `app-teardown-review/` in git instead of writing this ADR:** rejected — the teardown contains auditor scratch and screenshots; the durable outputs are the PRD decisions, which this ADR + config-reference + the qa/ checklist capture.
- **Adopt SF Symbols / add light mode / go native-settings to satisfy the checklist:** rejected as above — each trades a coherent, ADR-governed design language for checklist conformance.

## Consequences

- **Positive:** operator-paced rollout with per-behavior kill switches; deviations are now recorded decisions (auditable, revisitable) instead of silent drift; deferrals have named triggers instead of being quietly dropped; the Nutrition Label can be declared honestly (dark-only, custom icons acknowledged).
- **Negative / watch:** 30 new dark flags is real inventory — without the quarterly ship-by/kill-by review this becomes exactly the flag graveyard the teardown flagged (~20 pre-existing dark flags since April). The review convention is load-bearing; its first pass is due 2026-10.
- The gitignored audit source means future sessions must rely on this ADR + the config-reference table + `qa/accessibility-release-checklist.md` for teardown context once the branch merges.
