# Feature Scope — <feature name>

<!--
MANDATORY for every feature or change that adds/modifies user-visible behavior,
data collection, schema, or API surface — regardless of which pipeline the work
enters through (feedback item, NEXT.md queue, staged-work, direct ask).

Copy this template into the feature's home:
  - feedback items → docs/feedback/items/<id>-<slug>/scope.md
  - planned initiatives → docs/plans/<initiative>/scope.md
  - anything else → docs/plans/<short-name>/scope.md

RULE: every section is answered or explicitly WAIVED with a reason.
Silence is not a waiver. Waivers are surfaced to the operator before build starts.

EXPRESS LANE: the operator may exempt a change from this template entirely at
flow start ("quick fix", "just ship it") — see CLAUDE.md §Conventions "Feature
gates" → "Rigor is an operator decision". No scope.md then; a one-line
TEST_LEDGER note replaces it. Operator-declared only, never agent-selected.
-->

**Date:** YYYY-MM-DD
**Entry point:** feedback #NN / NEXT.md item / direct ask
**Builder:** <session/agent>
**Operator sign-off on waivers:** yes / not needed (no waivers)

---

## 1. Analytics scope

<!-- Answer against the event taxonomy (an-data-architect owns it).
     Every feature answers exactly one of a/b/c. -->

- [ ] **(a) New events specced:** name, properties, trigger moment, emitting client(s):

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | | | | |

  → follow-through: `docs/data-dictionary.md` (if stored), taxonomy doc updated.
- [ ] **(b) Existing events cover it** — name them and what question they answer: …
- [ ] **(c) WAIVED — no analytics needed because:** …

## 2. Schema & flag scope

- New/changed tables or columns: <list, or "none"> → `docs/data-dictionary.md` + migration entry reviewed
- New/changed feature flags: <list, or "none"> → `config/features.json` + `backend/feature_flags.py` `FLAG_KEYS` + `docs/config-reference.md`, default state + graduation criterion stated
- New env vars / `model_config` keys: <list, or "none"> → `docs/config-reference.md`; ship-the-knob: name the deploy-free rollback lever if the feature is risky

## 3. Evidence scope

<!-- D-056 (2026-08-15) retired Maestro and the simulator ENTIRELY: no flow authoring,
     no flow execution, no screens/ captures, for any change in any pipeline.
     Fill the rows below instead. Do not add a Maestro or capture row back. -->

- [ ] **Structural guard:** `mobile/tests/check-<name>.js` — pins: …
      (dependency-free so it runs under plain node; add the matching `npm run test:<name>`)
- [ ] **Unit tests:** backend pytest files added/updated: <list, or why none>
- [ ] **Code-walk proof:** file:line-cited trace for behavior that is not mechanically
      checkable — <paste or link>
- [ ] **Manual TestFlight checklist** (only when runtime proof genuinely matters):
      numbered steps + expected result, specific enough to catch a regression —
      this is now the ONLY runtime evidence mobile gets
- [ ] **WAIVED because:** … (e.g. backend-only; no user-visible surface)
- `testID`s added/renamed: <list> (must pass `mobile/scripts/testid-lint.sh`, still in CI)

## 4. Docs scope (MANDATORY — HLD / LLD / API)

<!-- Each row: "updated" with the section touched, or "n/a because …". -->

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | | |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | | |
| `docs/architecture.md` (module wiring / data flow changed) | | |
| `living-memory/HLD.md` (architecture genuinely shifted: new module, client, major flow) | | |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | | |
| `docs/glossary.md` (new domain term) | | |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | | |

## 5. Ship gate declaration

<!-- The simulator-gate tier matrix is RETIRED (D-056, 2026-08-15). There is no tier to
     declare and no qa/sim-runs/last-sim-run.json to write. -->

- **CI green:** `backend-tests` + `mobile-typecheck` (which also runs the `check-*.js`
  suites) + `maestro-testid-lint` — all passing on the pushed sha
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry naming what ran and what it proved
- **TestFlight verification** (if a checklist was written in §3): run by the operator, outcome
  logged in TEST_LEDGER
- Express lane declared by the operator? <yes + what was skipped / no>
