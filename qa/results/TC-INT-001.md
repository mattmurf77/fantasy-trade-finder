# TC-INT-001 — Sleeper-boundary input handling (G-003..G-008 gotchas)

| Field | Value |
|---|---|
| **Status** | PASS (8/8 checks) |
| **Date executed** | 2026-06-11 |
| **Layer** | integration |
| **Component(s)** | `session_init` roster sanitization; `/api/sleeper/user`, `/api/league/parse-url` passthrough |
| **Requirement / doc ref** | GOTCHAS.md G-004 (null slots), G-005 (string IDs), G-003 (name mismatch), G-006 (username case) |
| **Engine path & flags** | default; SQLite scratch |

### Objective
Verify the backend defensively handles untrusted Sleeper-shaped input without
crashing — the documented integration gotchas.

### Scope
- **In scope:** null roster slots, int player IDs, unknown/garbage IDs, empty
  roster, duplicate IDs at `session_init`; bad-username + URL-parse passthrough
  error handling.
- **Out of scope:** live Sleeper API contract (synthetic leagues 404); the
  DynastyProcess↔Sleeper name-matching loader (separate data-quality pass).

### Actual Result
**8/8 PASS.** Nulls filtered (3 valid + 2 null → 3). Int IDs coerced (no
TypeError). Garbage IDs filtered (2 valid + 3 junk → 2). Empty roster → session
still created. Bad username → 404 (graceful). parse-url → structured 400 for
both garbage and a URL the parser didn't recognize. Evidence:
`qa/sec/scratch_int/TC-INT-001-run.json`.

### Outcome
**PASS** — the Sleeper input boundary is robustly defended; the G-004/G-005
gotchas are handled (filter nulls, coerce IDs to strings).

### Findings requiring attention
| ID | Severity | Finding | Evidence | Suggested action |
|---|---|---|---|---|
| F-1 | **P3** | **Duplicate roster IDs are not deduped** — submitting 3 IDs twice yields a 6-entry `user_roster`. Harmless today (downstream set-izes for most ops), but a duplicated player could in principle be "given" twice in a generated package or double-counted in roster-strength analysis. | `dup-ids` check: 6 in roster | `dict.fromkeys()`-dedupe `user_player_ids` in `session_init` (one line); low priority. |

### Observations & feedback (no change required)
- **Input sanitization is consistent**: `[str(x) for x in ...]` coercion +
  `if pid in players_dict` filtering at every roster ingestion point means the
  pool is the single source of truth — unknown/null/typed IDs all funnel through
  the same gate.
- The passthrough endpoints fail *closed and structured* (404/400 JSON), so a
  flaky Sleeper response surfaces as a clean client error, not a 500 — good for
  the "Server is waking up" retry UX.
- The DynastyProcess↔Sleeper name-matching (G-003) wasn't exercised here; the
  live DB shows 0 unmatched in current data, but `dump_mismatches.py` remains the
  tool for that audit when the player pool refreshes.
