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

- [x] Structural guard: `mobile/tests/check-founder-rule-waterfall.js` (`npm run
  test:founder-rule-waterfall`; the choice gated on the server route, every catalog rule in the
  server's order executed against `backend/rule_catalog.py`, zero rows shown, words for
  `not_measured` / `not_run`, additions apart, note field / cap / Save wiring, drafts at page
  level, the leave guard, polling stops, numbers formatted). Wiring pass.
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
- [x] **Unit tests (wiring pass):** `backend/tests/test_founder_rule_waterfall_routes.py`: the
  founder gate on every route (9 refusal cases), the cron secret on the operator read, run
  lifecycle (202 → running → 409 → complete; the 60 s cap; unsupported; league not selected;
  restart → none), the run equals `rule_waterfall.compute` on a real job's inputs and its served
  count equals that job's published deck, the run writes nothing a real request reads and the
  next deck is unchanged, the job stops at the probe, the probe is one guarded call and a real
  job is byte-identical, notes through the routes, rate limit, operator read without account
  ids, aggregate-only output. Sabotage table in the wiring report.
- [x] **Manual TestFlight checklist** (founder account, `founder.review` on, account in
  `FOUNDER_ACCOUNTS`, a 12-team Sleeper league selected):
  1. Calibration → Founders' review: "Player labels | Trade rules" shows; Player labels is the
     label page as before.
  2. Trade rules before any run: every rule listed by stage with name and description, counts
     empty, "No run yet…" line; Run for this league is enabled.
  3. Tap Run: it reads "Running…" with a progress line; within about a minute the header reads
     "Started with N candidate trades → M served" with commas; the stage totals add up to N − M
     (minus any "+A added" line).
  4. "Revised offers" (when `trade.next_move` is on) reads "Not measured…", not 0; zero rows are
     visible and dimmer; "Hide rules that removed nothing" hides and restores them.
  5. Tap a row: full description, the note field. Type a question, scroll to another row,
     expand it, come back: the text is still there and the row says "Unsaved". Tap Player
     labels: an "Unsaved notes" alert; Keep editing keeps you here.
  6. Save: "Saved", then "Last edited by you · just now"; collapse: the row shows "Note". Edit
     and save again: "1 earlier version" lists the first text. Clear the field and save: the
     marker goes, history keeps both.
  7. Paste over 1,800 characters: the counter appears; the field stops at 2,000.
  8. While a run is in progress, start another from a second founder device or league: "Another
     run is in progress…" (409).
  9. Kill and relaunch the app: notes are still there; counts remain until the next deploy.
  10. A non-founder account: no Founders' review control. With VoiceOver on, a row reads "Fair by
      market value, removed 41,224, remaining 3,809" (numbers vary). At the largest Dynamic Type
      size rows wrap without clipping.
  11. During a run, open Trades on another device/account: the deck still arrives (slower for the
      run's duration at most).
- [ ] WAIVED: —
- `testID`s added: `founder-review.use.labels|rules`, `founder-rules.{loading,error,retry,league,
  header,headline,started-definition,run-at,added-note,no-run,running,problem,run,hide-zero,
  added,others}`, `founder-rules.stage.<stage>`, `founder-rules.row.<key>{,.toggle,.has-note,
  .status,.question,.note,.counter,.saved,.save,.history}` (no Maestro flow references them).

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated (wiring pass) | the five routes: `GET/POST /api/founder/rule-waterfall`, `GET/PUT /api/founder/rule-notes/<rule_key>`, `GET /api/admin/founder/rule-notes` |
| `docs/config-reference.md` | n/a because nothing new is configurable (the run cap, one-run lock and note rate limit are code constants; the gate is use case 1's) |
| `docs/runbook.md` | updated (wiring pass) | § Founders' review: reading the notes with the cron secret, run cost, symptoms |
| mobile docs | updated (wiring pass) | `mobile/src/components/CLAUDE.md` `founder/` row, `mobile/src/utils/CLAUDE.md`, `mobile/tests/README.md` |
| `living-memory/LLD.md` | n/a because this builder does not touch living-memory (operator instruction); the merging session adds the conventions: catalog-as-data with an AST completeness test, append-only notes |
| `docs/architecture.md` | updated | module table row + "Decline waterfall" paragraph after the rules-first section; wiring paragraph (wiring pass) |
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
- **TestFlight verification:** the checklist in §3 (operator, on the build carrying this).
- Express lane declared by the operator? no.
