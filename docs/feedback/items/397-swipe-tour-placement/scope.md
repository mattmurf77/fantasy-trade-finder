# Feature Scope — FB-397/#398 swipe-coaching beat pinned to top of screen

**Date:** 2026-08-24
**Entry point:** feedback #397 + #398 (Group B, 2026-08-24 wave; #398 supersedes #397)
**Builder:** Group B author agent (worktree `trading-engine-eval-8ab7bc`, branch `claude/new-user-feedback-55320e`)
**Operator sign-off on waivers:** not needed (no waivers — every section answered)

---

## 1. Analytics scope

- [x] **(b) Existing events cover it** — the guide engine already instruments every beat lifecycle, and this change alters only *where the bubble renders*, not any user action or step transition:
  - `guide_step_shown` (with `spotlight` outcome property) — fires when s2.2 becomes visible (`useGuide.ts:279, 447`); answers "did the beat render, and did its spotlight resolve".
  - `guide_step_advanced` (`via`) — fires on the real swipe (`useGuide.ts:480`); answers "did the user complete the coached action".
  - `guide_step_skipped`, `guide_step_suppressed` (`blocked_by`), `guide_tour_dismissed`, `guide_tour_reenabled`, `guide_tour_completed` (`useGuide.ts:491–530`) — unchanged escape/refusal/reset telemetry, including the Settings re-arm path the TestFlight checklist uses.

  None of these gain or lose properties. **No new events:** band placement is a render decision inside the overlay; there is no new user-observable action to instrument, and a "bubble position" property would be device-geometry noise the taxonomy has no question for. (This is answer (b), not a waiver — the existing events fully cover the behavior under change.)

## 2. Schema & flag scope

- New/changed tables or columns: **none** → `docs/data-dictionary.md` n/a
- New/changed feature flags: **none** — the pin rides the existing `onboarding.guided_avatar` / `onboarding.guide_v2` surface untouched; per-step data (`band: 'top'`) lives in the script table, which is code, not config → `docs/config-reference.md` n/a. Rollback lever: revert the one-line `s2_2` declaration (deploy-free is not applicable to a mobile binary; the change is also inert for every other beat by construction).
- New env vars / `model_config` keys: **none**

## 3. Evidence scope

- [x] **Structural guard:** extend `mobile/tests/check-guide-spotlight-tracking.js` (`npm run test:guide-spotlight-tracking`) — new cases **11n** (tall-ring input + `pin:'top'` → top pin), **11o** (null cutout + pin → pin still honored), **11p** (s2_2 builder declares `band:'top'`, AST-located), **11q** (overlay call site passes `active.band`); existing 11d–11h and the 11i/11j invariant sweep pin the 4-arg path byte-identical. Sabotage proofs + per-case self-satisfaction checks specced in [prd.md](prd.md) §6a. Guard is already dependency-free and runs the lifted solver under plain node.
- [x] **Unit tests:** none — backend untouched; the solver's executable coverage lives in the structural guard above (which *runs* the function, same rigor).
- [x] **Code-walk proof:** outlined in [prd.md](prd.md) §6b; written into status.md at build time with final line numbers.
- [x] **Manual TestFlight checklist:** [prd.md](prd.md) §6c — re-arm via the Settings Guided-tour toggle (verified path: `enableTour` → `resetGuideProgressV2`, `useGuide.ts:521–522`), s2.2 pinned top with Pass/Like visible, n12/n19/untargeted-beat regression spot-check, both mascots.
- `testID`s added/renamed: **none** (existing `settings.guided-tour-toggle`, `guide.overlay`, `trades.card-body` registrations referenced only) — `mobile/scripts/testid-lint.sh` still run pre-ship.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added/renamed/removed/changed — mobile-only render change |
| `living-memory/LLD.md` | n/a | no schema/route/invariant *convention* shifts; the guide-overlay placement contract is documented in `mobile/src/components/CLAUDE.md`, which IS updated (below) |
| `docs/architecture.md` | n/a | no backend module wiring or data-flow change |
| `living-memory/HLD.md` | n/a | no architecture shift — one optional field + one solver branch inside an existing component |
| `docs/cross-client-invariants.md` | n/a | no shared constant/enum/color touched; `BAND_EDGE` etc. are mobile-overlay-local |
| `docs/glossary.md` | n/a | no new domain term — "band" and "pin" stay internal to the overlay |
| ADR or `DECISIONS.md` entry | n/a | choice (per-step opt-in pin vs. solver heuristic vs. screen-side placement) is small-radius and fully argued with alternatives in this folder's [plan.md](plan.md) §3–4, the durable home for feedback-item rationale; no repo-wide convention is set |
| `mobile/src/components/CLAUDE.md` (not in the template table, added honestly) | **will update at build** | `AnalystGuide` row gains one clause: adjacency placement, with a per-step `band: 'top'` pin (#397/#398) — the row currently describes adjacency as the whole story, which would be stale after this change |

## 5. Ship gate declaration

- **CI green:** `backend-tests` (untouched, must stay green) + `mobile-typecheck` (`npx tsc --noEmit`, runs the `check-*.js` suites incl. the extended guard) + `maestro-testid-lint` — all on the pushed sha
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry naming the guard cases run, the five sabotage proofs, and the typecheck
- **TestFlight verification:** checklist in prd.md §6c handed to the operator; outcome logged in TEST_LEDGER
- Express lane declared by the operator? **No — full gates.**

## Coordination (build-order constraints)

- `mobile/src/screens/TradesScreen.tsx` is **READ-ONLY** for Group B — Group A owns it this wave. All three s2.2 touchpoints in it (request 3312–3318, advance ~4335, registration 3221/3243) are deliberately untouched.
- `mobile/tests/check-guide-spotlight-tracking.js` is **also extended by Group D** — serialize the merges; the file already uses case IDs through 11m and a rule 12 (12a) exists, so Group D must not claim 11n–11q.
