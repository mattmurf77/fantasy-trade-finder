# Scoring context deployment and recovery record

Local date: 2026-09-04 (deployment activity uses 2026-09-05 UTC).
Status: merged and live; post-deployment smoke checks passed. Temporary worktrees
and the merged local implementation branch were removed after verified content
and recovery-tip capture.

## Release candidate

| Tip SHA | Branch | Worktree |
|---|---|---|
| `a3911d2f6aabc9154ab32a2c2b7a8f98091246be` | `codex/scoring-execution-context` | `/private/tmp/ftf-scoring-execution-context` |
| `606e512cd87f692eced3b92ccadb4f0192ea3449` | detached baseline | `/private/tmp/ftf-scoring-baseline` |

[PR #277](https://github.com/mattmurf77/fantasy-trade-finder/pull/277) contains
request-local scoring selection and accepted trade-job context capture. It adds
no resources, dependencies, migration, algorithm change, feature cuts, or
separate worker. [Implementation evidence](https://github.com/mattmurf77/fantasy-trade-finder/blob/a3911d2f6aabc9154ab32a2c2b7a8f98091246be/docs/plans/budget-scalability/implementation.md)
records the code walk, deterministic concurrency tests, and local test limits.

## Pre-deployment evidence

- PR CI: [run 33941624088](https://github.com/mattmurf77/fantasy-trade-finder/actions/runs/33941624088).
  Mobile typecheck and all mobile structural checks, web structure, and test-ID
  lint passed. Full backend suite completed before merge: **4629 passed / 1
  skipped**, 618.28 seconds. All four required jobs passed on the reviewed head.
- An independent final-source deployment review passed 127 context/API tests.
- Live Render service: `srv-d7g37ftckfvc73a32gvg`, Oregon, linked to `main`,
  automatic deploy on commit, Standard plan, one instance. The API returned
  `numInstances: 1` and no autoscaling configuration. Start command:
  `gunicorn run:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120`.
- Existing live commit: `606e512cd87f692eced3b92ccadb4f0192ea3449`, deploy
  `dep-dacrjrhsrm7s73c3gabg`. This is the known pre-release rollback target.
- Read-only pre-release smoke checks passed: `/` 200, `/api/feature-flags` 200,
  `/api/tier-config` 200, and unauthenticated `/api/trades/status?job_id=deployment-smoke`
  401 with the expected session-expired response. No identity or device headers
  were sent. Feature flags and tier configuration captured for after comparison.
- The live plan is already Standard ($25/month for this one web instance at
  currently verified prices); the checked-in blueprint still says Free.
  This deployment will retain the live configuration and add no paid services.
  Existing other services and metered usage are additional; this is not an
  enforced $200 total invoice cap or a verified 10,000-user capacity claim.

## Deployment and content verification

PR #277 squash-merged at `2026-09-05T03:33:55Z` as
`db6b3a1756fa9a1662fa9f1916c718353a3c7af5`. The base remained `606e512c` and
the checked head remained `a3911d2f` immediately before merge.

Render automatically started deploy `dep-dador97avr4c73ak0sr0` at
`2026-09-05T03:33:56Z` and finished at `2026-09-05T03:35:08Z`. The API reports
`live` with the exact merged SHA. The three existing cron services also report
`live` at that SHA: hourly `dep-dador9favr4c73ak0svg`, realtime
`dep-dador9favr4c73ak0t1g`, daily `dep-dador9navr4c73ak0t30`. Deployment success
does not assert that a scheduled notification run was manually triggered.

All four post-release read-only smoke checks passed with the expected status and
response shape. Feature flags and tier configuration match the pre-release
baseline. Homepage and unauthenticated status response hashes also match. No
authenticated account was used or modified by these checks. Render configuration
was reread after deployment: Standard, one instance, no autoscaling configuration,
and the identical single-worker start command. No live settings were changed.

After fetching `origin/main`, `git diff --exit-code a3911d2f origin/main` produced
no differences. Both complete Git trees are
`1764e139b2f9d817f41f0eca58a00ff3d6d4e12f`. This verifies content equality rather
than relying on ancestry across a squash merge. The implementation worktree is
clean. The clean detached baseline is exactly the old main SHA in the table; it
was created solely for regression comparison and has no unique work to retain.

The release gate used the completed PR CI on the tree identical to merged main.
No production load test or authenticated generation smoke is claimed. The
implementation record's original local-review status is historical; this record
and the merged PR carry the subsequent deployment evidence.

## Recovery

Recreate the implementation branch with
`git branch codex/scoring-execution-context a3911d2f6aabc9154ab32a2c2b7a8f98091246be`.
Recreate the detached baseline with
`git worktree add --detach /private/tmp/ftf-scoring-baseline 606e512cd87f692eced3b92ccadb4f0192ea3449`.

## Cleanup

Tips and content-verification evidence captured before deletion on local date
2026-09-04. Both temporary worktrees were successfully removed without `--force`;
no uncommitted work was discarded. The local `codex/scoring-execution-context`
branch was deleted at tip `a3911d2f`; `git branch -D` was appropriate because this
was a squash merge with complete content equality verified above. The remote PR
branch remains available as an additional recovery reference.

The original user's dirty checkout remains in place; no unrelated work was
included in the deployment branch. The release record, SCALABILITY_REVIEW, and
new CHANGELOG/TEST_LEDGER entries are local write-back changes in that checkout;
they were not combined with its unrelated changes or pushed. The merged PR body
also records the final CI and live-deployment evidence durably on GitHub.
