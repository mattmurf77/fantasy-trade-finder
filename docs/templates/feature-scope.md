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

HOW TO FILL IT (section by section, plus the product acceptance pass):
  .claude/skills/pm-technical/references/scope-block.md

EXPRESS LANE: the operator may exempt a change from this template entirely at
flow start ("quick fix", "just ship it") — see CLAUDE.md §Conventions "Feature
gates" → "Rigor is an operator decision". No scope.md then; a one-line
TEST_LEDGER note replaces it. Operator-declared only, never agent-selected.
-->

**Date:** YYYY-MM-DD
**Entry point:** feedback #NN / NEXT.md item / direct ask
**Strategy owner:** operator ask "<quote>" (YYYY-MM-DD) / `models-lead` (packet: <path>) / strategy note accepted by `head-product` (<path>, YYYY-MM-DD)
**Builder:** <session/agent>
**Operator sign-off on waivers:** yes / not needed (no waivers)

---

## 1. Analytics scope

<!-- Answer against the event taxonomy: backend/analytics_taxonomy.py
     (analytics-lead grants changes to it). git grep every event name you cite;
     never invent one. Every feature answers exactly one of a/b/c. -->

- [ ] **(a) New events specced:** name, properties, trigger moment, emitting client(s):

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | | | | |

  → follow-through: `docs/data-dictionary.md` (if stored), taxonomy doc updated;
  registered in `backend/analytics_taxonomy.py` and classified against
  `analytics_queries.NON_INTENT_EVENTS` in the emitter's commit;
  `analytics-lead` grant attached: <path>.
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

- **CI green:** `backend-tests` + `mobile-typecheck` (which also runs every `check-*.js`
  suite) + `web-structure` + the testid-lint job (`maestro-testid-lint` — a legacy job
  name; it runs only `testid-lint.sh`, Maestro itself stays retired) — all passing on
  the pushed sha
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry naming what ran and what it proved
- **TestFlight verification** (if a checklist was written in §3): run by the operator, outcome
  logged in TEST_LEDGER
- Express lane declared by the operator? <yes + what was skipped / no>

## 6. Flow, states & reviews

<!-- Full UX review (ux-lead) is triggered by: a new visible entry, a tab or IA change,
     a deep link, a new interrupt, or a new screen's states. A flag-dark registration
     gets a light check at registration and the full review at flag flip.
     Any UI change gets a design review (design-lead, Chalkline). -->

- **UX review (`ux-lead`):** attached: <path> / light check (flag-dark): <path> / waived because …
- **Design review (`design-lead`, Chalkline):** attached: <path> / waived because …
- **States covered** (behavior, or "n/a because …" per row):

  | State | Behavior |
  |---|---|
  | First-run | |
  | Empty | |
  | Loading | |
  | Error | |
  | Offline | |
  | Flag-off | byte-identical to today / stated difference: … |

- [ ] **WAIVED because:** … (e.g. backend-only; no user-visible flow or screen)

## 7. Platform scope

<!-- Per platform: the reads and writes this feature uses, and how it behaves there.
     Fleaflicker is dark (`fleaflicker.link` false) — n/a unless this change lights it. -->

Guidance: [platform-parity.md](../../.claude/skills/pm-technical/references/platform-parity.md) (owned by `platforms-pm`).

| Platform | Reads / writes used | Behavior: parity / honest `platform_unsupported` / fallback copy / n/a |
|---|---|---|
| Sleeper | | |
| ESPN | | |
| MFL | | |
| Fleaflicker (dark) | | |

- [ ] **WAIVED because:** … (e.g. no league data read or written)

## 8. Model-visible change

<!-- Does this change what a model outputs (ranking, tiers, matchups, values, trade
     scoring/packaging, deck rules, outlook, pick values), or how model output is shown?
     If yes, fill a packet in the format of
     .claude/skills/pm-technical/references/model-change-packet.md and attach both of
     models-lead's sign-off lines: plan (13a) before the build, routed
     head-product → head-bizops; result (13b) on models-eng's eval output before
     ship, routed head-eng → head-bizops. -->

- **Model-visible?** yes / no — because …
- If yes:
  - **Model:** …
  - **Packet:** <path>
  - **`models-lead` plan sign-off (13a), before build:** attached: <path, date> (via `head-product` → `head-bizops`)
  - **`models-lead` result sign-off (13b), before ship:** attached: <path, date> (via `head-eng` → `head-bizops`)
