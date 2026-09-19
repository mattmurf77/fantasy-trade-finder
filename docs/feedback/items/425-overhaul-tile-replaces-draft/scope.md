# Feature Scope — G-425: Team overhaul hero replaces the Draft button (#425 + #426)

**Date:** 2026-09-08
**Entry point:** feedback #425 + #426 (mattmurf77, 1.17.2 build 154, TradesHome) — batch plan [422-win-now-ffv3-unavailable/plan.md](../422-win-now-ffv3-unavailable/plan.md)
**Builder:** G-425 build agent on `claude/feedback-422-428` (planner: this doc + [prd.md](prd.md) + [investigation.md](investigation.md))
**Operator sign-off on waivers:** not needed (no waivers) — but PRD Q1 (red requires a design-system addition) is an operator decision surfaced before build; default is the ice hero.

---

## 1. Analytics scope

- [ ] (a) New events specced: none.
- [x] **(b) Existing events cover it.** `overhaul_started` (`backend/analytics_taxonomy.py:1407`, props `league_id`, `outlook`, `entry`) already fires on the Start tap from the host (`TradesScreen.tsx:7066`, `entry: 'trades_home_card'`) and answers "did the landing entry get used". The hero keeps the same handler and the same `entry` value so the funnel does not split across builds. The Resume tap is navigation only today and stays that way. No new emitter, no taxonomy change, no `NON_INTENT_EVENTS` change.
- [ ] (c) WAIVED: n/a.

## 2. Schema & flag scope

- New/changed tables or columns: **none**.
- New/changed feature flags: **none**. The hero reads the existing `overhaul.enabled` gate unchanged (`TradesScreen.tsx:7060`); the Draft cell removal is unconditional (PRD R-6) so no flag is added or re-purposed; `draft.room` / `draft.tab` untouched.
- New env vars / `model_config` keys: **none**. Rollback lever = `overhaul.enabled` off (hero disappears; landing is today's minus the Draft cell and the card).

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-team-overhaul.js` §3 rewritten (PRD "Regression guards"): 3a single hero mount above `modeBarWrap` and above `TeamReviewEntryCard`, inside the main scroll; 3b gate unchanged; 3c Draft cell + `onDraft` absent from `TradeHomeUtilityRow` and its mount; 3d mode-bar `DRAFT_CHIP` + `onDraft` pass still present; 3e one `HERO_TONE` with `fill: ice.base`, no `flare` import, no hex literal, `radii.` only, `minHeight: 64`. Existing `npm run test:team-overhaul` script already present. Neighbouring guards that must stay green: `test:presentation-v2`, `test:receipts`, `test:finder-conditions`, `test:trades-banner-region`, `test:team-review`, `test:inline-home`, `test:calc-merged-layout`.
- [x] **Unit tests:** none — no backend change (why none: client layout only).
- [x] **Code-walk proof:** [investigation.md](investigation.md) §1–§2 (cohort → utility row → Draft cell; landing order with file:line for every block) and PRD R-1/R-2 (Toast offset still clears the hero because it sits above the measured wrapper).
- [x] **Manual TestFlight checklist:** PRD "TestFlight checklist" (5 steps) — runtime proof matters here because the change is visual placement.
- [ ] WAIVED: n/a.
- `testID`s added/renamed: **none**. `overhaul.entry-card`, `overhaul.entry-start`, `overhaul.entry-resume` are kept; `trades.home-utility.draft` is **removed** (no test or flow references it). `mobile/scripts/testid-lint.sh` still in CI.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route change |
| `living-memory/LLD.md` | n/a | no schema/route/invariant convention shifts; the entry-placement convention lives in BUILD-CONTRACT §9 (below) |
| `docs/architecture.md` | n/a | no module wiring change |
| `living-memory/HLD.md` | n/a | no architecture shift |
| `docs/cross-client-invariants.md` | n/a | no shared constant/enum/colour changed (ice tokens already there; no new hue) |
| `docs/glossary.md` | n/a | no new term |
| ADR or `DECISIONS.md` entry | **updated** | new D-entry: "overhaul hero is ice, not red/flare; red needs a design-system addition; fill isolated in `HERO_TONE`" + placement supersedes D9's "directly after Team review" |
| `docs/plans/team-overhaul/BUILD-CONTRACT.md` §9 | **updated** | entry row: "full-width hero above the utility row / mode bar, replaces the strip cohort's Draft cell"; guard paragraph: new §3a–3e wording |
| `docs/design/components.md` | **updated** | new "Hero entry tile" row (ice fill, `type.heading` title, min 64pt, radius 8, one per screen, whole tile pressable) — a new component variant |
| `mobile/src/components/CLAUDE.md` `:79`, `:90` | **updated** | OverhaulEntryCard row (placement + hero) and TradeHomeUtilityRow row (two cells; Draft removed by #425) |
| `docs/config-reference.md:417` | **updated** | strip description no longer lists Draft |
| `docs/plans/team-overhaul/mockups/entry-mock-evidence.md` | **updated** (one line) | note that #425 superseded the "after Team review" proposal |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (runs the `check-*.js` suites) + `maestro-testid-lint` on the pushed sha.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry naming the guard assertions run and the code-walk; `FTF_SKIP_SIM_GATE=1` per D-056 with the evidence named.
- **TestFlight verification:** PRD 5-step checklist, run by the operator on the next build; outcome logged in TEST_LEDGER.
- Express lane declared by the operator? **no** — full gates.
