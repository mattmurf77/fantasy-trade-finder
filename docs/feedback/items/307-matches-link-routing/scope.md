# Feature Scope — #307 matches-tile league scoping + #308 contrarian fold-line honesty

**Date:** 2026-08-13
**Entry point:** feedback #307 + #308 (LeagueHome group, 2026-08-13 wave — both fast-track bugs)
**Builder:** wave-league build agent (plan: `plan-2026-08-13.md`, committed `6368e31`)
**Operator sign-off on waivers:** carried in the committed plan (§3.4, §4.5, §6); the #308 Maestro waiver was **voided at build** per the plan's own void clause — see §3 below.

---

## 1. Analytics scope

- [x] **(c) WAIVED — no analytics needed because:**
  - **#307** (plan §4.5, verbatim basis): the tap is already instrumented —
    `league_home_action_tapped {action: 'matches_mutual' | 'matches_awaiting'}`
    (`LeagueScreen.tsx`, registered taxonomy). Post-fix, scoped landing is
    deterministic given the tap, so a landing event measures nothing the tap
    doesn't. Adding a prop to a registered event is a taxonomy change — out of
    fast-track scope by the bright line.
  - **#308** (plan §3.4, verbatim basis): copy-honesty fix; no new user
    action, no decision this event stream would inform. The fold line has
    never been instrumented; adding events to it now would be net-new taxonomy
    work on a fast-track bug. No existing event changes shape.

## 2. Schema & flag scope

- New/changed tables or columns: **none** (zero backend changes; the fields consumed were already in the `/api/league/contrarian` response)
- New/changed feature flags: **none**
- New env vars / `model_config` keys: **none**

## 3. Test scope (mobile test platform)

- [x] **New flow:** `mobile/.maestro/flows/league/07-matches-tile-scoped.yaml` — #307: tile-tap lands on Matches scoped to the seeded league (segment + league chip both `selected`), then the `at` re-fire contract (toggle chip to All by hand → tab back → re-tap → rescopes). **Merge-gated on the Matches group's §4.3 chip-testID edit** (`matches.league-chip.*` allow-listed pending that build); never executed on-sim (D-P1-08).
- [x] **Extended flow:** `mobile/.maestro/flows/smoke/09-league.yaml` — one-line `assertVisible: id: league.progress-foldline`. **This voids the plan §6 #308 waiver via its own void clause:** the waiver assumed forcing <3 in-format ranked members hermetically meant reshaping shared fixtures; in fact the `standard` profile already seeds exactly 2 in-format ranked users (`qa_standard` + `qa_opp_ranked`, per `backend/tests/fixtures/profiles/standard.json`) < 3, so the fold line renders in the hermetic world as-is.
- Remaining #308 behavioural verification (per plan §6): node suites S1–S6, below.
- `testID`s added: `league.matches-mutual-tile`, `league.matches-awaiting-tile` (LeagueScreen tiles), `league.progress-foldline` (LeagueProgressModule) — `testid-lint.sh` OK. Referenced-not-added: `matches.league-chip.all` / `matches.league-chip.<league_id>` (Matches group's file, allow-listed with a note naming the constructing edit).
- **Capture delta:** none run — D-P1-08 retired the screen-capture/sim apparatus; the fold-line copy change would otherwise touch `league` captures.
- Smoke-suite impact: only `smoke/09-league.yaml` crosses this surface (extended as above). Not executed (D-P1-08).
- Backend: no pytest delta — zero backend changes.
- Node suites (all green on the final tree, every sabotage proven RED first, `git diff --quiet`-guarded per mutation):
  - `check-league-unlocks.js` (extended): S1 static-string revert, S2 needed ignored, S3 format clause dropped, S4 threshold drift — 21 checks
  - `check-contrarian-format-key.js` (new): S5 queryKey loses `activeFormat`, S6 fold props unwired — 3 checks
  - `check-matches-tile-league-param.js` (new): S7 half-fix (a tile drops `leagueId`/`at`), S8 tile testID stripped — 6 checks

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route or response change — fields consumed were already in the `/api/league/contrarian` response (plan §7 optionally proposes enriching that row with the insufficient-payload shape; orchestrator's call) |
| `living-memory/LLD.md` | n/a | no convention shift — extends the existing FB-91 param pattern and the existing pure-utils test idiom |
| `docs/architecture.md` | n/a | no wiring change |
| `living-memory/HLD.md` | n/a | no architecture shift |
| `docs/cross-client-invariants.md` | **proposed, not edited** (shared doc — orchestrator applies; text in `status-2026-08-13.md`) | new § "League unlock thresholds" + format display labels `1qb_ppr→"1QB"`, `sf_tep→"SF TEP"` now that two surfaces render them |
| `docs/glossary.md` | n/a | no new domain term |
| ADR / `DECISIONS.md` | n/a | no non-obvious choice — copy family and shapes are the committed plan's |
| `mobile/src/components/CLAUDE.md` | updated | `LeagueProgressModule` row — fold line dynamic |
| `mobile/src/utils/CLAUDE.md` | updated | `leagueUnlocks.ts` row — `contrarianFoldLine` / `CONTRARIAN_UNLOCK_USERS`, conflation warning kept |

## 5. Ship gate declaration

- **Simulator-gate tier:** none run — **D-P1-08** (2026-08-12) retired the Maestro/simulator apparatus as standing policy; TestFlight is primary QA. Verification is the static battery: `tsc --noEmit`, `testid-lint.sh`, four existing `check-*` suites (regression), three new/extended suites (30 checks), 8 named sabotages RED-then-green.
- Evidence: TEST_LEDGER entry at wave close (orchestrator); no `qa/sim-runs/last-sim-run.json` written — not fabricated.
- Operator deviation: D-P1-08 is the standing operator decision covering the absent sim run; the plan's §2 sim-gate language predates its enforcement here and is superseded by it.
