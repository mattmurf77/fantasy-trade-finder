# Feature Scope — Trade presentment rules (G6: #304, #336, #339, #340, #341)

**Date:** 2026-08-16
**Entry point:** feedback #304 + #336 + #339 + #340 + #341 (2026-08-16 wave, group G6)
**Builder:** G6 Author agent (this doc set); build agents per [batch-plan.md](batch-plan.md)
**Operator sign-off on waivers:** REQUIRED — two waivers below (§1 analytics, §3 Maestro per D-056) surfaced before build

---

## 1. Analytics scope

- [x] **(c) WAIVED — no new analytics events because:** the feature is
  backend-only with no user-interaction change — nothing new for a client to
  emit, and no request/response field changes (prd R-10). Measurement is
  covered without the taxonomy: (i) **per-rule kill counters** in the per-job
  structured log line + `presentment-tripwire` WARNING (prd R-9) — the same
  gate-kill-counter pattern the trade-relevance P0 work established, queryable
  in Render logs; (ii) **deck-eval counters** added to `scripts/deck_eval.py`
  (prd DB-1..DB-4) for distributional before/after; (iii) downstream user
  behavior (swipe outcomes on the improved decks) is already captured by the
  existing server-side `trade_decisions` / `user_events` recording — no new
  question needs a new event. If the operator instead wants kill counts in
  the analytics warehouse, the an-data-architect taxonomy gets a
  `trade_presentment_kill` server-side event — deferred unless asked.

## 2. Schema & flag scope

- **New/changed tables or columns:** none. R4 reads existing
  `trade_decisions` + `trade_matches` only → `docs/data-dictionary.md` n/a.
- **New/changed feature flags:** `trade.presentment_rules` →
  `config/features.json` + `backend/feature_flags.py` `FLAG_KEYS` +
  `docs/config-reference.md`. **Default state: recommended ship ON**
  (Q-G6-3, argued with rollout step in [prd.md](prd.md) §6 — operator
  decides; bright line acknowledged: this is a flag-surface change, so the
  ship-state needs an explicit operator yes). Graduation criterion: after
  DB-2 bands + one clean TestFlight checklist + two quiet weeks of tripwire,
  the flag is graduation-eligible (shed at a later cleanup; knobs remain the
  per-rule levers).
- **New env vars / `model_config` keys:** 7 model_config keys (lld §2:
  `max_overpay_frac`, `max_overpay_min_value`, `pos_net_cap`,
  `pick_gap_frac`, `pick_gap_min_value`, `need_gate_min_value`,
  `need_gate_upgrade_margin`), all DB-seeded → `docs/config-reference.md`.
  **Ship-the-knob rollback lever:** each rule dies live via
  `PUT /api/admin/config/<key>` (disable values in lld §2); whole group via
  the flag (one-line commit). No env vars.

## 3. Test scope (mobile test platform)

- [x] **WAIVED (Maestro + simulator) because:** D-056 retired Maestro/sim
  entirely, for any change ("no flow authoring, extension, or execution…
  for any change, in any pipeline"). Replacement evidence per D-056:
  - Backend pytest: `backend/tests/test_presentment_rules.py` (new) —
    U-R1..U-R10 in [prd.md](prd.md) §3.1, every behavioral test
    sabotage-proven; plus the flag-OFF byte-identity test.
  - Distributional: deck-eval replays DB-1..DB-4 with two-sided bands.
  - Code-walk proof CW-1 (file:line trace of all six generator paths),
    committed to this folder.
  - Runtime: operator TestFlight checklist, [prd.md](prd.md) §3.4 (6 items).
- `testID`s added/renamed: none (no client change).
- **Capture delta:** none — no visual change.
- Smoke-suite impact: none run (D-056); historical flows untouched.
- Backend pytest files added/updated: `test_presentment_rules.py` (new);
  possible fixture touch in `test_user_gain_gate.py`'s golden-deck helpers
  (reused pattern, not changed behavior).

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated (build)** | `/api/trades/generate` behavior note: presentment rules + flag + "deck may shrink; no contract change". No route added/renamed/removed. |
| `living-memory/LLD.md` | **updated (build)** | convention note: construction-gate vs presentment-filter layering; never-relaxed list grows; windowless exclusion-set pattern. |
| `docs/architecture.md` | **updated (build)** | § Request lifecycle (trade card — v2 engine): add the construction-rule hook + eligibility exclusion lines (honest call: the gate stacks are existing structure, but a named two-part layer spanning all generators + presentment is flow-diagram-visible and belongs in the lifecycle). |
| `living-memory/HLD.md` | **n/a because** no new module, client, or major flow — the layer extends existing generator gate stacks and dedup; architecture.md's lifecycle note covers it. |
| `docs/cross-client-invariants.md` | **n/a because** no shared constants/enums/colors — all 7 thresholds are server-resident model_config; clients never see or duplicate them. |
| `docs/glossary.md` | **updated (build)** | "presentment rules", "construction rules", "eligibility rules" (+ "pick-is-the-gap" if kept as a term). |
| ADR or `DECISIONS.md` | **updated (build)** | DECISIONS.md entry records: filter-not-reorder supersession (operator, batch-plan § G6); the arbitrated targeted-vs-untargeted R-5 boundary + its one-sentence asymmetry rationale; R-5's consensus-board choice (user-board variant = named follow-up); unresolved-window fail-open; Q-G6-1..3 outcomes. Itemized in prd §6 "Recorded decisions". |
| `docs/config-reference.md` | **updated (build)** | 7 model_config rows (following the `filler_min_frac`/`likes_you_min_user_delta` row format) + the flag row. |
| `docs/runbook.md` | **updated (build)** | `presentment-tripwire` grep + response (which knob to turn per rule). |

## 5. Ship gate declaration

- **Simulator-gate tier:** n/a — D-056 retired the simulator gate;
  `FTF_SKIP_SIM_GATE=1` is the standing pre-push posture. Replacement gate:
  pytest green + DB-1/DB-2 bands + CW-1 committed, then operator go/no-go
  with the TestFlight checklist post-deploy.
- **Evidence:** TEST_LEDGER entry (pytest counts + deck-eval run ids +
  band results); no `qa/sim-runs/` artifact (historical per D-056).
- **Operator deviation from the matrix:** none beyond D-056 itself (which
  redefined the matrix); flag ship-state ON is the one item needing an
  explicit operator yes (§2).

## Waivers requiring operator sign-off (summary)

1. **§1 analytics** — no new analytics events; measurement via structured
   log counters + deck-eval + existing server-side recording.
2. **§3 Maestro/simulator** — waived per standing D-056 (operator's own
   ruling; listed for completeness, not really discretionary).

Open decisions travelling with this scope (argued in prd §6): Q-G6-1
(likes-you gets R-4 only — confirm), Q-G6-2 (declined matches don't
hard-exclude — confirm), Q-G6-3 (flag ships ON — decide). **Resolved in
round 1:** the G4 cross-group question — orchestrator arbitration adopted
the targeted-vs-untargeted boundary (R-5 bypasses on any targeted job,
server-derived; R-1..R-4 apply everywhere); see prd §6 and
reconciliation-log.md.
