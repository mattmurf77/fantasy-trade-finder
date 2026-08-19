# Recovery ledger — `claude/team-review-analysis-plan-1f91e3` / worktree `jolly-leakey-d20295`

**Date:** 2026-08-19
**Session:** Team Review planning (#357/#358/#359) + `outlook.odds` lighting (D-094)

---

## Capture (recorded BEFORE any deletion, per `docs/recovery/CLAUDE.md`)

| Item | Value |
|---|---|
| Branch | `claude/team-review-analysis-plan-1f91e3` |
| Tip sha | `19d0dcf89b158dc6918e22c74fea01576379ab3e` |
| Worktree | `.claude/worktrees/jolly-leakey-d20295` |
| Forked from | `origin/main` @ `50e0451` |
| Merged via | PR #142 (`6a3eab3`), PR #143 (`e65bca1`), PR #144 (`8d0bff5`) |

## Verification — **by content**, not by ahead-count

This repo squash-merges, so `git branch -d` refusals and ahead/behind counts are
not evidence. `git diff origin/main <branch>` is also **not** clean here, and
that is expected rather than alarming: `origin/main` moved ahead during this
session (a concurrent session merged `ship/armed`, bringing bake-off,
likes-you-gates and consensus-balance-claim work). The diff is dominated by
what **main gained**, not by what the branch is missing.

Verified per-artifact instead, against `origin/main` after the last merge:

| Artifact | On `origin/main`? |
|---|---|
| `config/features.json` — `outlook.odds` | **`true`** |
| `backend/tests/fixtures/flags/{release,onboarding-v2,profiles-on}.json` | all three **`true`** |
| `mobile/tests/check-outlook-bands.js` | present |
| `backend/tests/test_outlook_route_cache.py` — the two rewritten guards | 3 matches for `test_flag_off_still_closes_the_route` / `test_flag_on_the_route_is_reachable` |
| `mobile/package.json` — `test:outlook-bands` script | present |
| `docs/config-reference.md` / `docs/api-reference.md` — LIT prose | present in both |
| `living-memory/DECISIONS.md` — D-092 / D-093 / D-094 | all three present |
| `docs/feedback/items/357-team-review/` | present |
| `mockups/team-review-2026-08-19/` | present |

`docs/config-reference.md` and `mobile/package.json` were **also touched by the
concurrent session**, so both were re-checked individually after the final
merge; neither edit was clobbered.

**Live verification:** `https://fantasy-trade-finder.onrender.com/api/feature-flags`
serves `outlook.odds: true`.

## Release

EAS iOS **build 121 (v1.15.0)**, build id `ccc3cd57-7850-4f42-93b8-2b67aa524a21`,
built from `f1cb03e` (tree-identical to `main` at merge time), submitted to
TestFlight and accepted by App Store Connect (submission `769a6193`).

## Deletion status — **NOT deleted; owed**

The worktree still exists and **the session ran from inside it**, so it could not
remove itself. It also now carries a full `mobile/node_modules` (installed to run
`tsc --noEmit` and the structural suites, both previously unrunnable here).

Owed, by whoever picks this up — content is verified above, so it is safe:

```
git worktree remove .claude/worktrees/jolly-leakey-d20295
git branch -D claude/team-review-analysis-plan-1f91e3
git push origin --delete claude/team-review-analysis-plan-1f91e3
```

A `--force` refusal on the remove means uncommitted files — inspect before
discarding. This matters: 91 stale worktrees (8.6 GB) once broke an EAS upload.
