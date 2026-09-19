# Feature Scope — G9 Matches polish (#334 dismiss resurrect-race, #335 segment/chip counts)

**Date:** 2026-08-16
**Entry point:** feedback #334 + #335 (2026-08-16 wave, group G9 — canonical folder = lowest ID)
**Builder:** G9 build agent (Phase 2); this scope authored by the G9 author agent (Phase 1)
**Operator sign-off on waivers:** required before build — waivers W-1 (count-render analytics) and W-2 (no feature flag) below

---

## 1. Analytics scope

- [x] **(b) Existing events cover it** — verified against `origin/main @ 0b2dcee`:
  - `awaiting_trade_dismissed` — **server-fired** on the #318 dismiss route
    (`backend/server.py:13320`; registered `backend/analytics_taxonomy.py:433`).
    Answers "how often are awaiting rows dismissed". The client fires no event
    here (by design, `mobile/src/api/trades.ts` contract comment) — the fix
    does not change when the POST fires, only what renders meanwhile, so the
    event's meaning is unchanged.
  - `match_dismissed` — server-fired on the mutual dismiss route
    (`backend/server.py:13359`).
  - `match_dismiss_undone` — existing client event on mutual undo
    (`MatchesScreen.tsx:365`); awaiting undo intentionally fires nothing
    (prior written waiver, comment at `:365-369`) — unchanged.
- **W-1 — WAIVED: no count-render event for #335** because counts are pure
  presentation of data the client already holds: they inform no decision a
  list-length query on existing events can't answer, there is no taxonomy
  entry for them, and a per-render emitter would be ingest noise. If count
  engagement ever matters, the taxonomy owner (`/an-data-architect`) specs a
  tap-adjacent event then — nothing here forecloses it.

## 2. Schema & flag scope

- New/changed tables or columns: **none** → `docs/data-dictionary.md` n/a
- New/changed feature flags: **none**. **W-2 — WAIVED: no flag gate** because
  #334 is a bug fix restoring already-shipped intended behavior (instant
  dismiss under the existing `ux.swipe_undo` flag, which continues to gate
  the undo path), and #335 is presentation-only with no data or contract
  surface. Rollback lever = `git revert` of the single mobile commit; there
  is no server-side blast radius. (Bright-line check: no schema, API
  contract, flag surface, or analytics event is touched — Polish path
  confirmed, and verification found nothing forcing an upgrade.)
- New env vars / `model_config` keys: **none** → `docs/config-reference.md` n/a

## 3. Test scope (mobile test platform)

- [ ] ~~New flow~~ / ~~Extended flow~~ —
- [x] **WAIVED (Maestro) per D-056** (`living-memory/DECISIONS.md` § D-056,
  2026-08-15): no Maestro flow authoring, extension, or execution for any
  change. Replacement evidence, specced in `prd.md` § Test plan:
  - Executed unit tests U-1…U-5 on the new pure `matchesDerive.ts`
    (transpile-under-node idiom — mobile has no jest harness; named
    sabotages, proven-to-fail RED runs recorded in QA notes).
  - Structural suites: `check-awaiting-dismiss.js` + S-10a–e (existing 21
    assertions byte-unmodified; S-10c pins the B-1 unhide ordering with the
    "unhide before await" sabotage, S-10e guards the no-focus-refetch
    premise); new `check-matches-counts.js` with S-11a–f.
  - Code-walk proof CW-1 (`qa-code-walk.md`): file:line trace covering all
    six cache-repopulation paths P1–P6, the B-1 unhide ordering, guide-v2's
    off-screen `fetchQuery` (P6), and the unmounted-tab dual (NB-4).
  - Operator TestFlight checklist, 8 steps (prd.md), with the concrete race
    repro: dismiss during an in-flight refresh.
- `testID`s added/renamed: **none** (S-11f pins the existing three id
  families; `mobile/scripts/testid-lint.sh` must stay green)
- **Capture delta:** none — simulator captures retired per D-056; visual
  verification of the count construction is TestFlight checklist steps 7–8
- Smoke-suite impact: n/a per D-056 (`mobile/.maestro/` flows are historical
  artifacts, never run)
- Backend: pytest files added/updated: **none — no backend change** (#318
  route and `retracted_at` suppression verified correct and untouched:
  `backend/server.py:13254`, `backend/database.py:4648/6798/7090/7247`)

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added/renamed/removed/contract-changed; `/api/trades/awaiting/dismiss` and `/api/trades/awaiting` byte-untouched |
| `living-memory/LLD.md` | n/a | no schema/route/invariant convention shifts — reuses established grammars (TanStack optimistic-update + `cancelQueries` hygiene; mono-count construction) |
| `docs/architecture.md` | n/a | no module wiring or data-flow change (one mobile screen + one pure util) |
| `living-memory/HLD.md` | n/a | no architecture shift |
| `docs/cross-client-invariants.md` | n/a | no shared constant/enum/color: counts are client-derived lengths, colors are existing chalk tokens, no threshold |
| `docs/glossary.md` | n/a | no new domain term |
| ADR or `DECISIONS.md` entry | n/a | no non-obvious choice: render-layer suppression + cancelQueries is the canonical TanStack pattern; rationale recorded in `prd.md` (R-1…R-3) which is the durable record |
| `docs/design/components.md` *(added row — plan § Docs table)* | **update at build** | one line noting Matches segment pills / league chips carry inline Plex Mono counts per the mono-count convention (ScorePill/tier-header family) |

## 5. Ship gate declaration

- **Simulator-gate tier:** n/a — the pre-ship simulator gate is retired per
  D-056; `FTF_SKIP_SIM_GATE=1` is the standing posture for `githooks/pre-push`.
- Evidence: CI green (structural suites incl. the two G9 suites, testid-lint,
  `tsc --noEmit`) + `living-memory/TEST_LEDGER.md` entry recording the U/S
  suite results, sabotage RED runs, and CW-1 + operator TestFlight checklist
  outcome. No `qa/sim-runs/last-sim-run.json` (sim retired, D-056).
- Operator deviation from the matrix: none beyond the standing D-056 posture.

---

### Verification note (author, 2026-08-16)

Plan claims were re-verified against `origin/main @ 0b2dcee`; the client-only
/ no-new-API-field verdict **holds** — Polish path confirmed. Corrections
documented in `prd.md` §V (plan base label vs. actual cite revision; guide-v2
`fetchQuery` as repopulation path P6; jest → transpile-under-node;
`fonts.mono` → `fonts.data`; two cosmetic line-number drifts). File ownership
stays disjoint from G6 (backend): G9 touches only `MatchesScreen.tsx`,
`matchesDerive.ts`, the two test suites, `components.md` (one line), and this
folder + `../335-matches-filter-counts/status.md`.
