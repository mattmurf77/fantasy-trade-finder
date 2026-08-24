# Feature Scope — #395/#396 lineup-impact slot alignment + honest platform template

**Date:** 2026-08-24
**Entry point:** feedback #395 + #396 (Group C, 2026-08-24 wave; fast-track bug path, full gates)
**Builder:** Group C author agent → build agent (branch `claude/new-user-feedback-55320e`)
**Operator sign-off on waivers:** pending — one waiver below (§1c analytics), surfaced before build per the gate rule

---

## 1. Analytics scope

- [ ] (a) New events specced: none.
- [x] **(b) Existing events cover it / (c) partial waiver:** display-only fix — no new
  user action, surface, or decision point is created, so **no new events are needed
  (waived)**. The one adjacent event, `lineup_impact_unavailable` (fired by
  `InLeagueCalculator` when the server omits `starter_impact`), is unaffected: both fixes
  change the *content* of `starter_impact`, never its presence. Whether users still complain
  about lineup rows is answered by the feedback pipeline itself, not an event.

## 2. Schema & flag scope

- New/changed tables or columns: **none**.
- New/changed feature flags: **none**. Both fixes ship unflagged: they correct wrong display
  output (a phantom QB change; a fabricated WR3 slot) rather than adding behavior anyone
  could want the old version of. `trade.position_impact` (existing, ON) continues to gate the
  rank chip; R-6 only changes that chip's copy.
- New env vars / `model_config` keys: **none**. Rollback lever = revert the commit (backend
  display-only; no data migration, no client dependency on the new labels).

## 3. Evidence scope

<!-- Maestro/simulator sections dead per D-056 — skipped. -->

- [x] **Structural guard:** extend `mobile/tests/check-card-impact-order.js` — pins the R-6
      rank-chip `#` prefix, anchored to the rank literal itself (`position ?? ''} #${beforeRank}`
      + its `afterRank` twin, never a bare `#${`) (named sabotage: remove the `#` → red).
      No new `npm run` script needed (existing guard).
- [x] **Unit tests:** `backend/tests/test_power_rankings.py` (4 new alignment tests) +
      `backend/tests/test_trade_evaluate.py` (2 new: aligned display through Mode B; platform
      template has no WR3 + sf_tep variant; 1 updated expected value at :1034). Each proven
      red by the named sabotage in prd.md §4a. Baseline rerun 2026-08-24: 113 passed / 6.53s
      across the two suites.
- [x] **Code-walk proof:** outline in prd.md §4b; written with file:line citations at build
      time (evaluate Mode B → `_starter_impact` → `align_starter_slots` → labeling →
      `CardImpactBlock` changed-row filter).
- [x] **Manual TestFlight checklist:** prd.md §4c — superflex Sleeper league (one SF row
      naming Daniels; no phantom QB row; totals unchanged) AND an ESPN/MFL league (no "WR3";
      `FLEX1/FLEX2` labels). Covers both league types so the operator's pass also settles
      which league the #396 report came from.
- [ ] WAIVED: n/a — evidence rows above are filled.
- `testID`s added/renamed: **none** (`testid-lint` unaffected; CI keeps running it).

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated** (at build) | `/api/trade/evaluate` row: the route's response CONTENT changes shape-compatibly (same fields). Two edits: platform template description "QB/2RB/3WR/TE/FLEX" → QB/2RB/2WR/TE/2FLEX (+SUPER_FLEX for sf_tep), and a one-sentence `slots` note that before/after rows are pairwise-aligned to minimize displayed churn among value-identical assignments (totals/deltas unchanged). The current row literally documents the 3-WR template, so "n/a" is not available. |
| `living-memory/LLD.md` | n/a | No schema/route/invariant *convention* shifts — one pure helper and one constant inside existing seams. |
| `docs/architecture.md` | n/a | No module added/removed/re-wired; `power_rankings` ↔ `server` data flow unchanged. |
| `living-memory/HLD.md` | n/a | No architecture shift. |
| `docs/cross-client-invariants.md` | n/a | Slot labels are server-produced strings clients render verbatim (not a client-mirrored constant); the rank chip's copy is single-client. No shared enum/color/threshold touched. |
| `docs/glossary.md` | n/a | No new domain term ("slot alignment" stays an implementation phrase, not UI vocabulary). |
| ADR / `DECISIONS.md` | **DECISIONS.md entry at ship** | Non-obvious choice worth one D-entry: platform leagues get a 2-WR + 2-FLEX standard template (claims the app can stand behind: a flex can legally start a WR) rather than per-league real templates (#311 phase-2, deferred) — plus churn-minimizing display alignment is presentation-only by contract. No ADR (no architectural surface). |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (incl. `check-*.js` suites) +
  `maestro-testid-lint` on the pushed sha — required before merge to `main`.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry at ship naming the suites run,
  the new tests, and their sabotage names (repo sabotage discipline).
- **TestFlight verification:** prd.md §4c checklist to the operator with the v-next build;
  outcome (incl. which league #396 was) logged in TEST_LEDGER + status.md.
- Express lane declared by the operator? **No** — full gates (fast-track refers to the bug
  path's planning depth, not a gate exemption).
