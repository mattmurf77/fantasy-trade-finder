# Feedback batch 2026-08-10 — items #289–#294

Batch-level plan for the six items selected from the 2026-08-10 feedback run.
Per-group plans/PRDs live in each group's lowest-ID folder (linked below);
this file holds only the batch framing, grouping rationale, and file-ownership
map that keeps the parallel build lanes disjoint.

- **Branch:** `feedback-289-294`
- **Base:** `origin/main` @ `7cea1fa` (2026-08-10). The session's other
  checkout (`teardown-remediation`) is 188 commits behind and was NOT used —
  per CLAUDE.md §Conventions, all work branches from a freshly fetched
  `origin/main`.
- **Worktree:** `.claude/worktrees/fb-289-294`
- **Not selected:** #205 (design-tenets interview) — parked, awaiting operator
  answers to `docs/feedback/items/205-design-tenets/interview-questions.md`.

---

## Table of Contents
- [Groups](#groups)
- [File ownership](#file-ownership)
- [Cross-cutting notes](#cross-cutting-notes)

---

## Groups

| Group | Items | Path | Platforms | Folder |
|---|---|---|---|---|
| **G1 — MFL identity in the Draft Room** | #289 | fast-track bug | backend | [`289-mfl-draft-room-ids/`](../289-mfl-draft-room-ids/) |
| **G2 — Mock draft: engine, lifecycle, interactivity** | #290, #291, #292 | feature | backend → mobile | [`290-mock-draft-engine/`](../290-mock-draft-engine/) |
| **G3 — Pick value in subsets & position filters** | #293, #294 | polish | mobile | [`293-picks-in-subsets/`](../293-picks-in-subsets/) |

### Grouping rationale

- **G1** is independent of everything else — a backend identity-mapping fix on
  the draft board payload. Safe to run and ship alone.
- **G2** takes the feature path because its heaviest item (#290, a change to
  the CPU pick model's *form*) drags the group up. #290 and #292 both live in
  `backend/mock_draft_service.py`, so they get ONE owner and are serialized —
  #291 root-cause first, then #292's lifecycle fix, then #290's engine change
  (which needs a working second-mock loop to iterate against).
- **G3** is two items with one root: draft-pick value is excluded from the
  Starters/Bench subsets and position filters by an explicit current design
  decision. The operator reversed that decision, so both items resolve under a
  single rule and a single file owner.

### Operator rulings captured at selection

1. **G3 contract:** *"I'm talking about picks for value."* → a team's
   draft-pick value contribution is **subset-independent and
   filter-independent**; switching to Starters/Bench or filtering by position
   must never silently drop a team's draft capital from its value. This
   reverses the design recorded in `LeagueSummaryScreen.tsx` (~L159-162,
   "Picks are neither starters nor bench, so the Picks key only exists in the
   All subset").
2. **Scope:** G1, G2, G3 all selected for build. #205 parked.

### Operator rulings captured mid-Phase-1 (2026-08-10)

3. **G1 QA path — use the Dependables MFL league (62846).** Supersedes the
   proposed "no Maestro coverage possible" waiver. The mobile QA harness has no
   MFL seam (zero MFL refs in `test_users.py` / `qa/`; it is Sleeper-fixture
   driven), so no `mobile/.maestro/` flow is authored for #289 — but the
   acceptance surface is now a **live verification against the real league where
   the bug was observed**, which is stronger evidence than a fixture flow. The
   PRD carries an executable live-QA procedure with per-requirement pass
   criteria observed on that league. Planner spike S-2 (DP-crosswalk hit rate
   for MFL player ids) is folded into that QA pass against real data instead of
   running as a separate pre-build spike — which makes the specified
   crosswalk-miss fallback load-bearing: **a miss must never regress to a raw
   numeric id.**
   *Backlog spun out:* an MFL seam for the mobile QA harness, so this becomes
   an automated flow later.

4. **G2 scope addition — fix the duplicated name-vs-id defect.** G1's planner
   found `backend/mock_draft_service.py:1013` and
   `mobile/src/screens/MockDraftScreen.tsx:284` carry the SAME
   ids-instead-of-names bug as #289, in G2's lane. Operator ruled: **fix it.**
   It is not a separate feedback item, but it is very likely part of why the
   ffv3 mock read as "broken" in #290 — a board of numeric ids is hard to judge
   for realism. G2 owns the fix; G1 must not touch those files. G2's PRD
   carries it as its own numbered requirement with its own test, and should
   reuse whatever identity seam G1 establishes rather than inventing a second
   one (coordinate through the orchestrator, since the two lanes cannot see
   each other's diffs).

### Operator decisions at the Phase 1/2 boundary (2026-08-10)

Operator: *"Aligned to all recommendations but ship with G3 flagged."* All
orchestrator recommendations adopted, with one override (D-13).

| ID | Decision | Source |
|---|---|---|
| **D-5** | **G2 reach rule:** need DOMINATES reaching, but idiosyncrasy survives — a bot with no positional need may still occasionally reach. Rejected "only need drives reaching": need severity is ~0 for most (team, position) pairs in August (`VIABLE_ELO_FLOOR = 1280`), so that reading would make most bots draft strict BPA and the board chalky. | operator |
| **D-6** | **G2 tier walls:** hard wall in rounds 1–2; softer penalty in rounds 3+. Prevents the round-1 Tate case cold while keeping late rounds from collapsing to near-BPA. | operator |
| **D-7** | **#291 scope:** make the mock row's pick affordance VISIBLE before tap. Drafting for other teams is explicitly OUT — separate, much larger item, engine has no such call. | operator |
| **D-8** | **#292:** fix ALL THREE proven dead-ends; skip the diagnostic spike. | operator |
| **D-9** | **G2 tier shape:** adaptive (locally-significant gap vs. local median), NOT a fixed Elo threshold — the value curve flattens in the tail. "Tight groups of 4-5" is a TARGET the gap rule naturally produces, not a hard size clamp; a clamp would manufacture boundaries where the values have none. | orchestrator |
| **D-10** | **G2 re-validation:** run-and-record against a regression bar; no full re-fit / re-published artifact. Tripwire: `test_w2_16` asserts `all_pass is False` — if the fix makes the model pass, that test goes red and the full W2e re-fit becomes mandatory. Handle if it fires. | orchestrator |
| **D-11** | **G3 hermetic seeding:** Option B — seed-independent AST structural check + Tier A flows + written partial waiver + manual verification on a real league. Seeding `draft_picks` into `seed_ui_test_db.py` is a FOLLOW-UP, not part of a polish item. Rationale: the current seed writes zero `draft_picks`, so `hasPicks === false` and four planned tests are vacuous — one would pass with zero implementation. | operator |
| **D-12** | **G3 position-pill reversibility:** add an explicit exit rule so `{RB, PICKS}` → tap RB does not strand the user in a picks-only ranking. Provenance-tracking rejected as a hidden state axis. | operator |
| **D-13** | **G3 SHIPS FLAGGED** — *operator override of the orchestrator's unflagged recommendation.* This is a reversal of shipped behavior on a live surface, so it gets a kill switch. | **operator override** |
| **D-14** | **G3 analytics:** waiver ACCEPTED — no new events; taxonomy is default-deny and a new event needs four-touch registration. | operator |
| **D-15** | **Write the missing neutral-Picks rule into `docs/cross-client-invariants.md`.** The screen's comments cite that document as governing, but it does not actually contain the rule — a pre-existing gap this change widens. Orchestrator-owned file; applied at integration. | operator |
| **D-16** | **G2 absorbs the Mock Draft id→name fix** (`mock_draft_service.py:1013` fed from `server.py:11438`, `MockDraftScreen.tsx:284`). Without it, an MFL league's Draft Room shows franchise names while its Mock Draft shows ids — adjacent surfaces disagreeing. | operator |

**Known and accepted, not fixed this batch:** `original_username` stays null on
the MFL path, so traded MFL rows keep rendering `from —`. The honest fix is
client-side and would escalate G1 from sim Tier 3 to Tier 1. Named here so it
does not surprise anyone in the release note.

---

## File ownership

Disjoint across groups so the Phase 2 worktrees merge cleanly. Assigned up
front because a prior run's three agents independently edited the same shared
docs and produced trivial-but-real conflicts.

| Owner | Files |
|---|---|
| **G1** | `backend/draft_board_service.py`, `backend/mfl_service.py`, G1's own item folder |
| **G2** | `backend/mock_draft_service.py`, `mobile/src/screens/MockDraftScreen.tsx`, the `/api/mock-draft` shims in `backend/server.py`, G2's own item folder |
| **G3** | `mobile/src/screens/LeagueSummaryScreen.tsx`, G3's own item folder |
| **Orchestrator** | `docs/api-reference.md`, `docs/cross-client-invariants.md`, `living-memory/*`, `mobile/src/*/CLAUDE.md`, `config/features.json`, this file |
| **Harness lane** | `qa/sim-run.sh` (+ `qa/` as strictly required), `docs/runbook.md` § Pre-ship simulator gate |

**Ownership gap closed (D-17, orchestrator, 2026-08-10):** G2's Author found
`mobile/src/screens/DraftRoomScreen.tsx` and
`mobile/src/components/draft/MockEntryPanel.tsx` were assigned to **nobody**.
Both belong to **G2** — #291's affordance fix lives in `DraftRoomScreen.tsx:1325`
and #292's buttonless-error dead-end lives in `MockEntryPanel.tsx:90-96`.
G1 is backend-only and confirmed clear of both. Also G2's:
`mobile/src/components/draft/DraftRows.tsx`.

Shared docs are orchestrator-owned: build agents propose changes to them in
their `status.md` and the orchestrator applies them at integration. Any group
needing an edit outside its lane raises it rather than taking the file.

### `backend/server.py` — REGION ownership (orchestrator decision, 2026-08-10)

G1's plan surfaced a real collision: the MFL board fix needs ~5 lines inside
`_mfl_board_binding` (L10411-10493), while G2 owns the mock-draft route shims
(L11380+). The two regions are ~900 lines apart, so non-overlapping hunks
auto-merge cleanly.

| Region | Owner |
|---|---|
| `_mfl_board_binding`, ~L10411-10493 | **G1** |
| `/api/mock-draft` shims, ~L11380-11530 | **G2** |
| Anything else in `server.py` | orchestrator — raise it, don't take it |

**Rejected alternative:** G1's Option B (a defaulted `members_fn` fetcher
parameter) would have removed the shared-file edit entirely, but it costs a
redundant `load_league_members` query per board render and introduces a seam
whose only purpose is dodging a merge. That is the speculative abstraction
`docs/coding-guidelines.md` §2/§3 prohibits; a 900-line separation does not
need an architectural workaround. If the merge does conflict, the orchestrator
resolves it by hand — cheaper than the permanent seam.

Both build agents must `git merge-base` check their branch before integration:
a prior run's agents silently branched 4 commits behind HEAD.

---

## Cross-cutting notes

- **Report-vs-code drift is the default assumption.** All six items were filed
  against TestFlight **1.11.0**; `origin/main` has moved 188 commits since this
  session's other checkout, and the draft surfaces changed heavily in that
  window. Every plan answers "does this still reproduce on current
  `origin/main`?" with file:line evidence *before* proposing a fix. #291 is the
  likeliest already-fixed / never-broken item — `MockDraftScreen.tsx` is
  documented as the one surface that accepts picks.
- **Flag state on the base commit:** `draft.room`, `draft.mfl`, `draft.mock`,
  `draft.rank_inline`, `draft.manual_picks`, `draft.tab` are all **true**;
  `CPU_MODEL_VALIDATED = True` in `mock_draft_service.py`, so mocks do serve
  bot picks rather than the typed-empty refusal.
- **Worktree hygiene:** this batch's worktree is swept at ship time per
  CLAUDE.md §Conventions — content verified on `origin/main`, sha recorded in
  `docs/recovery/`, then removed. Not left behind.
