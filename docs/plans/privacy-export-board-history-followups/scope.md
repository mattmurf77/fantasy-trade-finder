# Scope — account-export privacy and board-history deletion fencing

2026-11-04. Bug fixes on freshly fetched main `065a1ee6`. Current open PRs
were checked first (54); no overlapping implementation was found. This work
is authorized by the launch follow-up request, with no production actions.

## Behavior

Account export keeps owned rows, history metadata, actions, own rankings and
public trade packages while withholding internal mixed-owner generation
payloads. Prepared recovery payloads already follow this rule. Extend it to
raw diagnostic, bakeoff, candidate, page-cache and packed-evidence payloads;
filter inline feature/valuation partner evidence consistently with existing
redaction rules. Unknown/malformed private JSON is withheld, never passed
through as raw text. Read-only export must not mutate stored evidence.

Board-history writes lock and validate each actual private-board owner,
not only the user triggering a league sync. A deleted owner is skipped;
a concurrent deletion either wins first or deletes the committed snapshot.
Guard input freshness against deleted/re-created owners using current board
source timestamps. Preserve other managers, formats and upsert precedence.

## Analytics/schema/flags

No new collection, event, table, column, flag, model knob or dependency.
Privacy corrections are unconditional. No provider calls, purchases, live
DB operations, builds, production settings or main merges are in scope.

## Evidence

Targeted synthetic export and deletion-race tests, existing account rights,
board-history and scrub suites, and disposable PostgreSQL concurrency tests.
Negative controls must show the leak/race before the fix. Full CI is required
on the PR. Backend only: no mobile UI or TestFlight flow changes; device and
simulator evidence is inapplicable (D-056).

## Documentation

Update API export contract, architecture/private-board writer invariant,
data dictionary (payload visibility, no schema change), plan index and test
ledger. HLD, client invariants, glossary and ADR are inapplicable: no new
architecture, client contract constant or domain term. Review release
privacy/safety checklist and record adjacent actionable gaps/activation gates
separately, without treating old plans as current production evidence.

## Code-walk and validation

- `backend/accounts.py:1520`: internal mixed-owner payload columns are omitted
  centrally before any row leaves export. `:1561` withholds malformed inline
  JSON and hidden partner/debug fields; `:1579` reuses engine valuation
  redaction; `:1639` removes unoriented shared-match valuation. Owner/alias
  selection, credentials exclusions, packages/actions and stored data remain.
- `backend/database.py:15396`: caller guard remains first; SQLite also fences
  no-caller weekly writes. `:15416` locks actual owners in stable order;
  `:15420` re-reads the captured board source through the same connection;
  mismatched timestamp/rounded Elo or missing owners skip before any write.
- Final scoped SQLite run: **237 passed, 2 PG-only skips in 22.87 s**, across
  export/history, account rights/deletion, roster history, session-init
  deletion fencing, diagnostic storage, evidence retention and analytics
  bearer safety. Disposable socket-only PostgreSQL new suite: **10 passed
  in 2.61 s**, including both caller and no-caller owner-lock/deletion races.
- Three named negative controls fail at their intended assertions:
  `diagnostic-payload-pass-through` (1 failure),
  `inline-private-json-pass-through` (1 failure),
  `held-owner-validation-disabled` (2 failures). Source restored afterward.
- Privacy-manifest and EAS-exclusion guards pass; tracked feature JSON is
  byte-for-byte unchanged. Diff whitespace check passes. No full local suite.

See [scoped release checklist](release-checklist.md) for adjacent policy and
operator/device evidence items; the documented pre-scrub serving window is
unchanged by agreement with the launch coordinator. CI/review remain pending.
