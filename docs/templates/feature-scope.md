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

## 3. Test scope (mobile test platform)

<!-- Every user-visible mobile change ships with a Maestro delta. -->

- [ ] **New flow:** `mobile/.maestro/<file>.yaml` — covers: …
- [ ] **Extended flow:** <existing file> — added steps: …
- [ ] **WAIVED because:** … (e.g. not mobile-visible; covered by smoke flow NN unchanged)
- `testID`s added/renamed: <list> (must pass `mobile/scripts/testid-lint.sh`)
- **Capture delta:** <screens to re-capture at ship, e.g. `trades`, `sheets/trade-dna` | none — no visual change> — run `mobile/scripts/screen-capture.sh --screen <x>` (see `docs/runbook.md` § Screen library)
- Smoke-suite impact: which of the 11 smoke flows cross this surface, and are they still green?
- Backend: pytest files added/updated: <list, or why none>

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

- **Simulator-gate tier** (per the matrix in `docs/runbook.md` § Pre-ship simulator gate):
  Tier: <1 full smoke + feature flow / 2 feature flow + affected smoke subset / 3 smoke subset / 4 none — CI only>
- Evidence: TEST_LEDGER entry + `qa/sim-runs/last-sim-run.json` written after the run
- Operator deviation from the matrix (if any) and why: …
