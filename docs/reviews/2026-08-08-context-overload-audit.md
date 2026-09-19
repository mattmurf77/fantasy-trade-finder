# Context-overload audit — 2026-08-08

Four parallel auditors measured what every Claude session ingests before doing work
(tokens ≈ chars/4), and what tree/doc structure costs during work. This report is the
durable record; the remediation shipped the same day on branch `context-slim-2026-08-08`.

## Measured baseline (before remediation)

| Component | Tokens |
|---|---|
| Root CLAUDE.md | 2,840 |
| SessionStart hook injection (HANDOFF 89% + NEXT 88% full-text) | 2,210 |
| 41 project-skill `description:` frontmatters (always-on) | ~7,400 |
| Four mandated living-memory reads (naive: CHANGELOG full = 12.9k) | 6,900–19,700 |
| **Session start total** | **19,400–32,200** |
| Mobile session adds `screens/`+`components/`+`navigation/` CLAUDE.mds | **+27,600** |

Key structural findings:

1. **Double payment:** the hook injects HANDOFF+NEXT, then CLAUDE.md mandated re-reading
   both (~2,470 tok pure duplication per session).
2. **Wrong slope:** CHANGELOG grew ~405 tok/entry with a per-entry TOC *in front of* the
   newest entry; projected session start ~53k tok at +6 months. No retention/rotation
   rule existed anywhere in the layer.
3. **Inverted orientation:** `mobile/src/{screens,components}/CLAUDE.md` were 25k tokens
   of per-issue changelog (136 dated entries; one row 5,857 chars; 2 duplicated rows),
   while `backend/` (17.8k-line `server.py`), `web/`, `extension/` had none.
4. **Search surface:** naive filesystem search saw 468,311 files vs 1,188 tracked
   (84% = `.claude/worktrees/`, 8.4 GB, 56 worktrees). `mockups/trade-calc/node_modules`
   (307 MB) untracked-but-not-ignored.
5. **docs/ (968k tok of markdown):** none of the 7 core reference docs had a TOC
   (`config-reference.md`: 80k chars behind 4 H2s). `docs/plans/` held ~111k tok of
   confirmed-dead plans with no archive convention — and `plans/README.md`+`CLAUDE.md`
   falsely claim status/round files are gitignored. Feedback duplicate-check cost
   8–110k tok (114 folders, no index, 5 status formats, 9 missing status.md).
6. **Skills:** 35 role skills (single commit 2026-07-18, zero edits since, ~22 total
   deliverables) cost 7.5k tok of always-on description; 5 memo-role skills had zero
   outputs ever. Skill *bodies* are lazy-loaded — only frontmatter is always-on.
7. **Stale-fact traps (0 token cost, correctness cost):** `living-memory/HLD.md` still
   asserted Sleeper-only scope; `SUBAGENT_PRINCIPLES.md` linked nonexistent paths;
   `docs/README.md` described a tree two generations old; tuning constants live
   unlinked in 3 files (glossary / config-reference / cross-client-invariants).
8. Out-of-repo but dominant: ~150 plugin skill descriptions (legal/finance/marketing/…)
   load into every session — larger than the entire in-repo skill cost. Operator lever:
   disable unused plugins.

## Remediation shipped (this branch)

- **Boot contract:** hook injects HANDOFF (≤2KB) + NEXT queue + CHANGELOG top-2 +
  GOTCHAS index slice; CLAUDE.md declares a zero-read start + pull-on-demand table +
  `git grep`/`git ls-files` search convention.
- **Retention (FORMAT.md §Retention & Rotation, enforced via `living-memory-format-check`):**
  CHANGELOG keeps last 10 entries (≤1,200 B each), older → `living-memory/archive/`;
  per-entry TOCs banned in append files (grouped/bottom index only); GOTCHAS gets a
  marker-delimited index table; TEST_LEDGER capped ~2 months; HANDOFF ≤2KB, NEXT ≤1.5KB.
- **Orientation:** mobile screens/components CLAUDE.mds rewritten as present-tense
  indexes (history stays in git log); new `backend/`, `web/`, `extension/` CLAUDE.mds;
  "not-for-code-work" stubs in `docs/business/`, `docs/reviews/`, `docs/design/`,
  `mockups/`, `archive/`, `reference/`, `qa/`; `docs/CLAUDE.md` + `docs/README.md`
  refreshed to the real tree.
- **Findability:** TOCs added to api-reference / config-reference (+H3→H2 promotion) /
  data-dictionary / runbook; `docs/feedback/items/INDEX.md` generated + status lines
  normalized going forward + 9 missing status.md backfilled.
- **Skills:** 35 role-skill descriptions trimmed to ≤250 chars; 5 zero-output skills
  retired to `archive/skill-workspaces/`.
- **Hygiene:** `mockups/*/node_modules/` + `docs/design/icon-explorations/` gitignored.

**Target after remediation: ~6–8k tokens at session start, flat over time; mobile
sessions save a further ~22k; route/flag/schema sessions save ~20–25k via TOCs.**

## Deferred (tracked in NEXT.md / this report)

- `docs/plans/_archive/` sweep of the ~111k tok of dead plans (list in §5 above);
  fix the gitignore-lie in `plans/README.md`/`CLAUDE.md`.
- Tuning-constant de-dup (make config-reference §model_config sole authority);
  competitor-material index (~112k tok across 4 locations).
- Worktree relocation/sweep (56 remain; verdicts in `2026-08-08-branch-triage.md`).
- `living-memory/` static-file fold-in (HLD/LLD are contractually live via feature-gate
  #3 — folding requires editing that rule; HLD/LLD content refresh needed regardless).
- Root cleanup of untracked scratch in the primary checkout (12 PNGs, `.DS_Store`,
  `secrets.local.env.bak`).
- Operator: disable unused claude.ai plugins (largest single lever, outside the repo).
