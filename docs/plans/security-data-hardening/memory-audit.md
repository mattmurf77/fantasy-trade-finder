# Scoped memory format audit — 2026-09-05

Applied the repository's living-memory-format-check skill to the five changed memory files. Checked headers, required sections, navigation presence and docs link targets. The table's severity is the skill's **format severity**, not a software/security release verdict. Existing historical navigation/ID drift was not rewritten.

| File | Severity | Drift items |
|---|---|---|
| HANDOFF.md | ✅ clean | Current-state overwrite, required template, labels, links and 2,000-byte cap checked. |
| HLD.md | ❌ blocking | Pre-existing human-readable H1 differs from the literal filename required by the format rule; required sections and docs links pass. |
| LLD.md | ❌ blocking | Pre-existing human-readable H1 differs from the literal filename; required sections and docs links pass. |
| DECISIONS.md | ❌ blocking | Pre-existing nonliteral H1 and four missing historical docs targets. Bottom index is allowed by FORMAT retention rules; new D-183 is unique and indexed. |
| TEST_LEDGER.md | ❌ blocking | Pre-existing nonliteral H1 and three missing historical docs targets. Required sections and new security links pass. |

Count: 1 clean, 0 minor, 4 blocking under the strict format labels. This is a scoped check, not certification of every historical TOC anchor or ID sequence.

The missing historical targets are `docs/plans/landability-challenger/PRD.md`, `docs/reviews/2026-08-18-trade-logic-archaeology.md`, and `docs/reviews/2026-08-18-valuation-age-audit.md`; DECISIONS also references the missing `docs/plans/landability-challenger/scope.md`.

Possible separate fixes: reconcile the format rule with the established human-readable H1 convention, and recover or replace the missing historical links from their original workstream. No such cleanup was applied in this security task. The current handoff was overwritten because the repository's session contract explicitly requires that, independently of format cleanup.
