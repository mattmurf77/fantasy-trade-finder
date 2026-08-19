# Recovery ledger — Settings IA sweep (2026-08-19)

> Capture-then-delete. Verified **by ancestry AND by content** against `origin/main`
> (`git log origin/main..HEAD` = 0 commits; `git diff origin/main HEAD` = empty),
> not by ahead-counts or a `branch -d` refusal.

| Worktree | Branch | Tip | Landed as |
|---|---|---|---|
| `…/5c245f45-…/scratchpad/wt-settings-ia` | `feat/settings-ia-hub` | `8692fb5` | fast-forward `28c12a0..8692fb5` → `main` |

## Where the work landed

- 8 commits, fast-forwarded onto `main`. Settings becomes a hub page plus seven
  second-level pages under `mobile/src/screens/settings/`, and moves off
  `presentation: 'modal'` to a pushed page ([D-089](../../living-memory/DECISIONS.md)).
- Flag `account.settings_hub`, default **OFF**. **Deploy verified by content, not by
  assumption:** prod `/api/feature-flags` returns HTTP 200, serves 174 flags, and
  reports `account.settings_hub: false` — the key exists (so the deploy landed) and is
  off (so the hub is dark). Both halves checked; a missing key and a false key look the
  same to a grep that only tests truthiness.
- **TestFlight build cut:** EAS build `ba340395-0e5f-40c4-ad74-0a81184966ac`,
  **1.15.0 build 120**, submitted to App Store Connect 2026-08-19 and accepted.
  Unlike a backend-only change, `main`'s mobile tree DID move here, so a build was
  required — the presentation flip ships to every tester regardless of the flag.

## Two traps this sweep hit, for the next one

**1. `git rebase` dropped a commit and reported it as empty.** Rebasing `ecdbcb3` →
`28c12a0` (27 commits of concurrent work), git paused with "nothing to commit, working
tree clean" on the phase-0 commit and it was discarded on `--continue`. It was not
empty: it carried 15 mobile source files plus the flag registration. `tsc` caught the
loud half (22 `TS2307`s). The quiet half was worse — the flag ended up registered in
`onboarding-v2.json`, `profiles-on.json` and `config-reference.md` but ABSENT from
`config/features.json`, `FLAG_KEYS` and `release.json`, which would have shipped a dead
flag and a red mirror test. **Mid-rebase, "nothing to commit" on a commit you know had
content is a signal to stop and diff, not to continue.** Recovery is in `9a04ebc`.

**2. File-set parity is the check that catches it.** Comparing `git diff --name-only
<old-base>...<pre-rebase-tip>` against `git diff --name-only <new-base>...<post-rebase-tip>`
surfaced all 18 dropped files in one command — 3 of them (the flag registration) after the
first restore pass had already "fixed" the obvious 15. Eyeballing the diff would not have
found the second batch.

Restoring dropped files wholesale from the pre-rebase commit is only safe for files the
concurrent work did not touch. `config/features.json`, `backend/feature_flags.py` and
`backend/tests/fixtures/flags/release.json` all moved on `main` in the same window
(1.15.0, Today tab, bake-off), so those three had their one line re-applied surgically
instead — a `git checkout <sha> -- <file>` there would have reverted someone else's flags.

## Gates at merge

`tsc --noEmit` 0 · `testid-lint.sh` OK · `check-*.js` 60/60 ·
`pytest backend/tests` **3480 passed, 1 skipped, 0 failed**.
The 5 failures that blocked this branch earlier in the session were pre-existing on
`origin/main` and were repaired there in `70d1f3b`.

`FTF_SKIP_SIM_GATE=1` per the standing D-056 posture; evidence run in its place is the
three `check-settings-*.js` suites plus
[`../plans/settings-ia-hub/code-walk-proof.md`](../plans/settings-ia-hub/code-walk-proof.md).

## Still owed

**Runtime evidence.** Plan §9's 10-item TestFlight checklist is **unrun**. Build 120 is
the first time any of this has executed. The presentation flip reaches every tester
immediately and `account.settings_hub` does **not** roll it back — that is a build, not a
flag flip.
