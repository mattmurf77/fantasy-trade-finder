# Feature Scope — Founders' review, use case 2: the decline waterfall

**Date:** 2026-11-11
**Entry point:** direct ask (operator): "a table listing every yes/no rule structured in a decline
waterfall … the ability to comment or add questions to each yes/no rule as a free text field"
**Builder:** Claude Code session, worktree `feat/founder-rule-waterfall` (modules, storage, tests,
design). Route and page wiring: a later session, on top of use case 1's founder gate.
**Operator sign-off on waivers:** needed for §1 (analytics waived) and §3's TestFlight row
(deferred to the wiring pass); both stated below.

Design: [rule-waterfall-design.md](rule-waterfall-design.md).

---

## 1. Analytics scope

- [ ] (a) New events specced
- [ ] (b) Existing events cover it
- [x] **(c) WAIVED — no analytics needed because:** an operator-only diagnostic page used by one
  to three founder accounts; nothing is shown to users and no product decision rests on its
  usage. The notes themselves are the record (`founder_rule_notes`, append-only). If the wiring
  pass wants a usage count, `founder_waterfall_run` (properties: `teams`, `started`, `served`,
  `elapsed_ms`, `status`) would be the one event, specced against the taxonomy first.

## 2. Schema & flag scope

- New/changed tables or columns: **`founder_rule_notes`** (new, additive: `id`, `rule_key`,
  `user_id`, `body`, `created_at`; index `(rule_key, id)`), created by `metadata.create_all`, no
  `migration_cols` row, no existing row rewritten → `docs/data-dictionary.md` updated. Deleted and
  exported with the author's account (`accounts._ADDITIONAL_PRIVATE_TABLES`).
- New/changed feature flags: **none in this pass.** The page and routes ride use case 1's
  `founder.review` flag and `FOUNDER_ACCOUNTS` allow-list (default off; the kill switch is the
  flag).
- New env vars / `model_config` keys: none.

## 3. Evidence scope

- [ ] Structural guard (`mobile/tests/check-*.js`): n/a in this pass (no mobile code). The wiring
  pass adds one for the page (testIDs on the run button, rows, note fields).
- [x] **Unit tests:** `backend/tests/test_rule_catalog.py` (AST completeness both ways, the
  fixable-reason list against the page search's copy, row shape, plain-language lint),
  `backend/tests/test_rule_waterfall.py` (sums on 5 worlds incl. the fixture league under
  revisions 2 and 5; diagnostic deck = served rules-first deck card for card and proof for
  proof; served count = the real worker's published deck under production's flags; evaluator
  rows = the generator's own counts; no input or served-deck change; budget row; after-stage
  accounting; scope refusal; aggregate-only), `backend/tests/test_founder_rule_notes.py`
  (history, clear, cap, unknown key, author marker, additive table, account deletion/export).
  Each guarded behaviour proven red under a named sabotage (TEST_LEDGER entry by the merging
  session).
- [x] **Code-walk proof:** design §3.3–§3.4 (file:line-cited: where each count comes from, why
  the diagnostic's deck equals the served deck, what is not replayed).
- [ ] **Manual TestFlight checklist:** deferred to the wiring pass (no user-visible surface
  here). It must cover: run on a 12-team league, header line and sum, notes save / edit / clear
  and history, a second run while one is running (409), a non-founder account (404).
- [ ] WAIVED: —
- `testID`s added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a because no route ships in this pass; the two routes are specified in the design §7 and the wiring pass adds them here |
| `living-memory/LLD.md` | n/a because this builder does not touch living-memory (operator instruction); the merging session adds the conventions: catalog-as-data with an AST completeness test, append-only notes |
| `docs/architecture.md` | updated | module table row + "Decline waterfall" paragraph after the rules-first section |
| `living-memory/HLD.md` | n/a because no architecture shift: two leaf modules beside the worker, not wired |
| `docs/cross-client-invariants.md` | n/a because no shared constant or enum crosses clients |
| `docs/glossary.md` | updated | "Decline waterfall and rule catalog" |
| ADR or `DECISIONS.md` entry | n/a here; the merging session records the decision "the waterfall is a diagnostic full solve, not the served page's counts" (design §3.1) in DECISIONS.md |
| `docs/data-dictionary.md` | updated | `founder_rule_notes` |

## 5. Ship gate declaration

- **CI green:** `backend-tests` (full suite run in the worktree; counts in the builder's report)
  + `mobile-typecheck` + `maestro-testid-lint` (untouched by this pass).
- **Evidence recorded:** TEST_LEDGER entry by the merging session (sabotage table in the
  builder's report).
- **TestFlight verification:** after the wiring pass.
- Express lane declared by the operator? no.
