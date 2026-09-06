# Worktree and branch cleanup audit — 2026-09-04

> Complete read-only inventory and cleanup recommendations against live `origin/main` `606e512cd87f692eced3b92ccadb4f0192ea3449` (2026-09-03 14:18:19 -04:00). The audit agent made no branch/worktree changes. Execution by the parent task is recorded separately in [the dated recovery ledger](../../recovery/2026-09-04-branch-cleanup.md).

The full structured inventory (all refs, patch matches, changed paths, worktree states, and candidate manifests) is preserved in [the audit snapshot](../../recovery/2026-09-04-branch-audit-snapshot.json), independently of temporary working files. The parent executor additionally requires a whitespace-preserving aggregate-diff match or exact current-file blobs before deleting the content-equivalent batch; any stricter-proof mismatch is held and documented in the execution ledger.

## Outcome and scope

The initial enumeration found **449 local branches, 98 actual origin heads, origin/HEAD, one orphan agent372/composite tracking ref, and 24 registered worktrees** (22 existing directories plus 2 missing registrations). A concurrent security task created another local branch/worktree while the audit ran, so the complete branch snapshot below contains **450 local branches plus 100 remote-tracking refs**. Earlier progress messages said 23 worktrees; the complete parsed inventory corrects that count to 24.

**254 unpinned local branches** retain their exact commit and entire tree in main history. Another **111 unpinned local branches** have a complete branch delta matching a main commit, or every branch-touched file already identical to main. The mobile-B5 queue branch/worktree has a separate content-based supersession proof. **76 origin heads** qualify for cleanup (15 exact-history + 61 content-equivalent), after excluding every open pull request and all worktree-owner names.

The parent confirmed **366 local branch deletions (254 exact-history + 111 content-equivalent + the mobile-B5 queue branch), the mobile-B5 worktree removal, and pruning exactly 2 missing worktree registrations while retaining their branches**. All 111 additional local candidates passed the parent's stricter whitespace-preserving aggregate-diff or exact-current-blob verification; none was held. The local snapshot immediately afterward had **84 local branches**. The remote batch is now also complete: **all 76 verified remote branches were deleted**, leaving **22 origin heads**. All 11 open PR heads and all 76 remote recovery refs were verified intact. The initial permission error was resolved by selecting the existing `mattmurf77` account only for the cleanup process. Recommendations below are historical pre-deletion records, not instructions to rerun completed deletions.

The main checkout is deliberately preserved at stale `session-2026-08-13-notif-ship` / `05e87d848aced60a094b6e0f8891b3b01d5d94a8`, with 224 status entries at the first snapshot. No content from this checkout was used as the current-product baseline. No credential contents were read or emitted; filenames only are listed.

## Verification and limits

- **E1 — exact committed content retained:** the branch commit is reachable from current main and its complete tree object ID is recorded below. Every historical file/blob remains recoverable through main. Current main can intentionally differ because newer commits changed it; this is retention of the exact original tree, not a claim of tip-tree equality.
- **E2 — base-tree equality:** the branch has no net file delta from its merge base with main. This resolves merge/cherry-pick residue without treating ahead counts as new work.
- **E3 — current content equality:** enumerate every path changed between merge base and branch tip using `git diff --name-only --no-renames`; every such path has identical content/mode/presence between branch and current main.
- **E4 — complete squash-content equivalence:** compute `git diff <merge-base> <branch-tip> | git patch-id --stable` and match it to the patch of an actual non-merge commit reachable from main. This compares the full net branch delta, including merge-resolution effects. Stable patch IDs ignore whitespace/line-number drift; the matched main SHA is supplied for independent reproduction.
- **E5 — unresolved:** full-delta equality did not pass. Per-commit patch equivalence was only a diagnostic, never sufficient alone to approve a branch with unmatched net content. The branch is held unless the explicit queue proof applies. A differing file is not itself proof of missing functionality.
- Worktree checks included tracked and untracked status, ignored-file names, registration existence, Git administrative lock/merge/rebase markers, and `lsof` process current-directory evidence. Absence of a process is not proof that a user has abandoned a task.
- Live `git ls-remote --heads origin` confirmed the main SHA and origin tips. `gh pr list --state open --limit 200` returned the 11 open PR heads below; none of the 76 proposed remote deletions is one of them.
- All applicable instructions in root `CLAUDE.md`, `docs/CLAUDE.md`, and `docs/recovery/CLAUDE.md` were read. Root and main recovery requirements agree: capture tips in a dated recovery ledger before deletion; preserve uncommitted content; verify content because this repository squash-merges.
- This is an inventory, not a code-change/test run. No production settings, builds, deployment, application code, or open PRs were modified by this audit.

## Concurrency finding

`codex/security-data-hardening-20260904` gained a worktree at `/private/tmp/ftf-security-hardening-20260904` between the initial branch manifest and deletion preflight. The parent's preflight rejected the original 255-branch batch before mutation, excluded that newly owned branch, and reduced the batch to 254. Preserve this branch and worktree. This race makes a fresh expected-SHA and worktree-ownership check necessary immediately before every local deletion. Remote deletion must use the exact expected-SHA lease shown later.

## Exact supersession and important holds

### Mobile B5 queue — safe, removal completed by parent

Tip `dc781ff5495f35f06ce5f5214f25f941fb188c50`, branch `feat/mobile-b5-trade-queue`, worktree `.claude/worktrees/agent-ae3050bc4e4ca4e49`.

The four changed files are `mobile/src/components/QueueChip.tsx`, `mobile/src/state/useTradeQueue.ts`, `mobile/src/shared/types.ts`, and `mobile/src/screens/TradesScreen.tsx`. QueueChip and useTradeQueue are byte-identical to their versions in main's PR #40 squash `247d9b5e52bd8e9ec0533d140f9e785642144f95`; useTradeQueue remains byte-identical on current main. QueueChip subsequently received the Chalkline reskin in `fed3a3be5d4bab8b6de5c2a22a39ade91f502098` and accessibility work in `1580064cb88cb2f86f0264b03f76d500e2266984`. The current QueuedTrade type remains at `mobile/src/shared/types.ts:422` with the additive optional match_id. Main retains the queue state/hydration at TradesScreen:1048, enqueue/dequeue/send-all helpers at TradesScreen:6095, and rendered QueueChip at TradesScreen:8846. Thus the old branch supplies no missing queue implementation.

Its only non-clean entry was an untracked **symlink**, `mobile/node_modules`, pointing to the main checkout's `mobile/node_modules`; no independent dependency tree or ignored files existed there. No process or Git lock used it. Parent preserved the tip as `refs/recovery/2026-09-04/mobile-b5-trade-queue` before removal. Removing the link does not remove the shared target.

### Team-count agent — committed fix superseded, dirty lockfile held

`worktree-agent-ac3579d0fd8f1d2d8` at `2b7eb33f4298ed700eff4f8d9c8c9645170b4d84` changes one team-count line. The full patch matches main commit `9aef5e1fbb4b50fb22e1abdb022643a455122021`. Main now improves the old `leaguemates_total + 1` rule by preferring `summary.total_teams`, retaining the same +1 fallback and loading placeholder (`mobile/src/screens/LeagueScreen.tsx:554`); its adjacent comment explains ownerless-roster undercounting. The worktree has a modified `mobile/package-lock.json` and ignored dependencies, so the worktree and branch are held until that local change is preserved or separately adjudicated.

### Website and ledger worktrees — committed contents redundant, local files held

`claude/website-updates-continue-c7942b` at `c9345ae5a31c99f96792f2477615d74fc733979d` has a tree identical to its on-main merge base `e16bb48755bd0a8ddaadc7de817da32dbd0bb987`; its 21 ahead commits add no net content. Its worktree still contains ignored data.

`ledger/2026-09-03-fb413-ship` at `1aede146919b9c896944ebd6c46398ab2e64f1d8` matches main squash `6ccd6698e97fbac9b37d31e451cf0132060e7b6c`. Its worktree contains ignored `secrets.local.env`, a database, and dependencies; preserve those files before any future removal.

### Clean main-identical worktrees still carry data

`compassionate-jones-ea8a0e` (detached) and `open-feedback-summary-b43796` (branch `claude/dynasty-consensus-rankings-update-2b8b02`) both exactly match current main. Both contain ignored `data/trade_finder.db`, `data/trade_finder.db-shm`, and `data/trade_finder.db-wal`; compassionate-jones also contains `data/.sleeper_players_cache.json`. A clean Git status does not authorize discarding these databases. Hold both until their local data has been preserved or proven disposable.

### Missing worktrees are open-work registrations, not obsolete branch content

The two missing scratchpad registrations were pruned only after recording their full tips. **Keep** `feat/fb417-pushed-deck-research` (`6cd5c4902ffa49e85f748969d58a5b48f82aafcc`) and `feat/fb418-backend-like-exclusion` (`77a4e33b1c08acda487892d77a9e204290ccd3ec`): their work participates in open PR #274 on `claude/new-user-feedback-06dabd`. The latter worktree is Git-clean but has ignored credentials and a database.

### Genuinely unresolved implementations and research

`infra/render-cron-migration` introduces `.github/workflows/render-cron.yml`, removes Render cron services from `render.yaml`, and changes the runbook. Current main still contains those Render services and lacks this migration; open PR #102 confirms it is not an obsolete merged branch. Keep it.

`chalkline-primitives` contains new SegmentedTabs.tsx and Spinner.tsx absent from main; its 30-file net delta is not equivalent. `mobile/yellow-followups` has an unmerged permissionStatus/denied-banner approach; main's existing getPermissionsAsync call is not proof that the whole feature shipped. `audit/perf-optimization` and `feat/wave1-perf` retain non-equivalent research/design files; the old triage already marked their disposition as an explicit open question. Keep these until a targeted content recovery/disposition review.

`p1-remediation-2026-08-11` has seven unmatched commits and 34 branch-touched files differing from main, including trade_found, Sleeper analytics, tests, and reference documents. Some ideas may have shipped via the current session branch or later work, but the complete branch delta was not proven redundant, so keep its clean worktree with ignored data.

The older [2026-08-08 triage](2026-08-08-branch-triage.md) supplies useful historic supersession descriptions for many April/May UI branches. This audit does not automatically convert those old verdicts into new deletion authority where current full-content equality could not be established. The complete unresolved path list below makes those remaining checks concrete.

## Open PR heads — preserve

| PR | Branch |
|---|---|
| [#274](https://github.com/mattmurf77/fantasy-trade-finder/pull/274) | `claude/new-user-feedback-06dabd` |
| [#224](https://github.com/mattmurf77/fantasy-trade-finder/pull/224) | `claude/trade-model-review-101bf7` |
| [#223](https://github.com/mattmurf77/fantasy-trade-finder/pull/223) | `claude/ledger-correction-partner-summary` |
| [#160](https://github.com/mattmurf77/fantasy-trade-finder/pull/160) | `claude/tweet-product-gap-review-266ff1` |
| [#147](https://github.com/mattmurf77/fantasy-trade-finder/pull/147) | `feat/fit-challenger` |
| [#141](https://github.com/mattmurf77/fantasy-trade-finder/pull/141) | `docs/ppg-impact` |
| [#140](https://github.com/mattmurf77/fantasy-trade-finder/pull/140) | `docs/card-evidence` |
| [#139](https://github.com/mattmurf77/fantasy-trade-finder/pull/139) | `docs/landability-challenger` |
| [#135](https://github.com/mattmurf77/fantasy-trade-finder/pull/135) | `claude/peaceful-keller-de2832` |
| [#102](https://github.com/mattmurf77/fantasy-trade-finder/pull/102) | `infra/render-cron-migration` |
| [#91](https://github.com/mattmurf77/fantasy-trade-finder/pull/91) | `claude/stoic-mccarthy-e56da9` |

## Worktree inventory

Paths, tips, commit dates, and status below are the initial snapshot, with the concurrent security worktree appended. `A/B` means commits ahead of / behind audited origin/main. All initial registrations had **no Git locks, MERGE_HEAD, rebase, cherry-pick, or revert markers**. Dirty lists and ignored names are expanded immediately below. Main checkout process evidence includes descendants in nested worktrees; individual worktree rows use their own paths.

| Worktree path | Branch / tip | Commit date | A/B | Status entries | Ignored entries | Process evidence / disposition |
|---|---|---|---|---|---|---|
| `/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder` | `session-2026-08-13-notif-ship` / `05e87d848aced60a094b6e0f8891b3b01d5d94a8` | 2026-08-15T19:38:36-04:00 | 9/421 | 224 | 73 | node_repl, zsh, Python, node, codex, git, lsof, disclaimer, claude |
| `/private/tmp/claude-501/-Users-teresadickens-Documents-Claude-Projects-Fantasy-Trade-Finder--claude-worktrees-happy-golick-345cf1/f75cd725-9d48-417e-a928-f0ff331ef022/scratchpad/wt-417` | `feat/fb417-pushed-deck-research` / `6cd5c4902ffa49e85f748969d58a5b48f82aafcc` | 2026-09-03T01:40:30-04:00 | 4/10 | missing | n/a | none observed; registration pruned; branch kept |
| `/private/tmp/claude-501/-Users-teresadickens-Documents-Claude-Projects-Fantasy-Trade-Finder--claude-worktrees-happy-golick-345cf1/f75cd725-9d48-417e-a928-f0ff331ef022/scratchpad/wt-d178` | `feat/fb418-backend-like-exclusion` / `77a4e33b1c08acda487892d77a9e204290ccd3ec` | 2026-09-03T12:42:11-04:00 | 13/5 | missing | n/a | none observed; registration pruned; branch kept |
| `/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/agent-a36aaf8ad623b3be3` | `feat/finder-config-and-draft-order` / `e174b2965864fbd0ce284a18203e2b96bd553eec` | 2026-08-08T15:21:35-04:00 | 2/629 | 1 | 18 | none observed |
| `/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/agent-ac3579d0fd8f1d2d8` | `worktree-agent-ac3579d0fd8f1d2d8` / `2b7eb33f4298ed700eff4f8d9c8c9645170b4d84` | 2026-06-08T16:11:51-04:00 | 1/1019 | 1 | 1 | none observed |
| `/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/agent-ae3050bc4e4ca4e49` | `feat/mobile-b5-trade-queue` / `dc781ff5495f35f06ce5f5214f25f941fb188c50` | 2026-05-20T13:05:32-04:00 | 1/1056 | 1 | 0 | none observed |
| `/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/app-launch-scorecard-356d64` | `claude/app-launch-scorecard-356d64` / `69dc0cae7db1cd41a522dfb7d33f280038d318c2` | 2026-08-27T11:41:54-04:00 | 0/53 | 5 | 0 | none observed |
| `/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/compassionate-jones-ea8a0e` | `(detached)` / `606e512cd87f692eced3b92ccadb4f0192ea3449` | 2026-09-03T14:18:19-04:00 | 0/0 | 0 | 15 | none observed |
| `/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/gracious-knuth-62ebbe` | `claude/gracious-knuth-62ebbe` / `359a0ff5344816e898a58bb62a6aaf0572f52d77` | 2026-08-09T23:15:08-04:00 | 0/528 | 8 | 13 | none observed |
| `/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/happy-golick-345cf1` | `claude/new-user-feedback-06dabd` / `cd1d243bfa59d4291729730166b5a16d167dfde3` | 2026-09-03T13:56:09-04:00 | 14/5 | 0 | 17 | none observed |
| `/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/jolly-leakey-d20295` | `claude/compassionate-wilbur-e00696` / `5472e7034f545d3af228f26799e21f81c993b9bb` | 2026-08-21T16:34:47-04:00 | 0/112 | 1 | 14 | none observed |
| `/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/modest-albattani-138a2d` | `claude/clever-pike-c7ecb9` / `8b7689a0f3a060f9b826079e65e4bc0b1f7e19d4` | 2026-08-19T00:39:08-04:00 | 0/245 | 15 | 14 | none observed |
| `/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/modest-cerf-12ce88` | `claude/suspicious-chaplygin-7dab59` / `cce8f0862ce813171e3612764c40468aa74f2e0c` | 2026-08-09T23:50:11-04:00 | 0/525 | 1 | 13 | none observed |
| `/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/monetization-features-feedback-a6fe77` | `claude/fleeced-trade-engine-balance-c0c75d` / `606e512cd87f692eced3b92ccadb4f0192ea3449` | 2026-09-03T14:18:19-04:00 | 0/0 | 16 | 16 | zsh, Python, disclaimer, claude |
| `/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/new-user-feedback-5fa613` | `main` / `1d0152fc8f70868000c96e53544e680287e9ced8` | 2026-09-03T13:32:24-04:00 | 0/2 | 0 | 17 | zsh |
| `/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/open-feedback-summary-b43796` | `claude/dynasty-consensus-rankings-update-2b8b02` / `606e512cd87f692eced3b92ccadb4f0192ea3449` | 2026-09-03T14:18:19-04:00 | 0/0 | 0 | 2 | none observed |
| `/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/sad-benz-9922d6` | `claude/beautiful-saha-65d7fb` / `7dfcd168d5e7fe0609e2533d779a691c41e09a43` | 2026-08-12T22:27:03-04:00 | 0/425 | 8 | 8 | none observed |
| `/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/team-outlook-experience-27a7a1` | `claude/team-review-analysis-plan-1f91e3` / `5aff1ce9ab6990900fdcb20ca2e80d6532e4a044` | 2026-08-22T10:45:44-04:00 | 2/107 | 3 | 14 | none observed |
| `/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/trade-model-review-101bf7` | `claude/website-updates-continue-c7942b` / `c9345ae5a31c99f96792f2477615d74fc733979d` | 2026-09-02T16:09:56-04:00 | 21/13 | 0 | 15 | none observed |
| `/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/unruffled-meitner-3596cb` | `ledger/2026-09-03-fb413-ship` / `1aede146919b9c896944ebd6c46398ab2e64f1d8` | 2026-09-03T00:19:51-04:00 | 2/9 | 0 | 17 | none observed |
| `/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/vibrant-allen-023c8f` | `claude/events-tracked-per-user-1110f1` / `af91d6f8225d662110e67188adee1705ce219d64` | 2026-08-29T12:41:55-04:00 | 0/38 | 2 | 2 | none observed |
| `/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/vigorous-chaum-272d92` | `claude/vigorous-chaum-272d92` / `ab9368f81aa580a007cc49c91240754206d3e1ec` | 2026-08-10T22:33:05-04:00 | 0/499 | 50 | 0 | none observed |
| `/Users/teresadickens/Documents/Claude/Projects/ftf-p1-remediation` | `p1-remediation-2026-08-11` / `5a4a63217cb824ddcb3202e1f5af75552b496cac` | 2026-08-12T23:00:47-04:00 | 7/425 | 0 | 14 | none observed |
| `/Users/teresadickens/Documents/Claude/Projects/ftf-render-cron-migration` | `infra/render-cron-migration` / `57300ae55db004d9981e4c375972701078459091` | 2026-08-09T22:34:45-04:00 | 1/531 | 0 | 0 | none observed |
| `/private/tmp/ftf-security-hardening-20260904` | `codex/security-data-hardening-20260904` / `606e512cd87f692eced3b92ccadb4f0192ea3449` | 2026-09-03T14:18:19-04:00 | 0/0 | 18 | 8 | none observed |

<details><summary>/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder — full local-state filenames</summary>

Tracked/untracked status:

```text
 M .claude/launch.json
 M .claude/settings.local.json
 M .claude/skills/feedback/lessons.md
 M .claude/skills/feedback/references/build-phase.md
 M .claude/skills/feedback/references/plan-phase.md
 M .gitignore
 M CLAUDE.md
 M docs/plans/archive/2026/competitor-feature-waves.md
 M README.md
 M archive/CLAUDE.md
 M archive/root-cleanup-2026-07/README.md
 M archive/skill-workspaces/README.md
 M backend/CLAUDE.md
 M backend/tests/fixtures/draft/README.md
 M context.md
 M docs/CLAUDE.md
 M docs/README.md
 M docs/business/README.md
 M docs/business/ops/app-store-prelaunch-checklist.md
 M docs/business/product/2026-08-13-dynasty-year-in-review-plan.md
 M docs/design/CLAUDE.md
 M docs/design/brand/README.md
 M docs/feedback/README.md
 M docs/feedback/items/README.md
 M docs/plans/CLAUDE.md
 M docs/plans/README.md
 D docs/recovery/2026-08-13-device-auth-s0-sweep.md
 M docs/recovery/CLAUDE.md
 M docs/reviews/CLAUDE.md
 M extension/CLAUDE.md
 M living-memory/CHANGELOG.md
 M living-memory/DECISIONS.md
 M living-memory/README.md
 M living-memory/TEST_LEDGER.md
 M archive/retired-tooling/mobile/maestro/README.md
 M mobile/CLAUDE.md
 M mobile/README.md
 M mobile/app.json
 M mobile/assets/CLAUDE.md
 M mobile/assets/README.md
 M mobile/ios/DTFDynastyTradeFinder/Info.plist
 M mobile/src/CLAUDE.md
 M mobile/src/README.md
 M mobile/src/api/CLAUDE.md
 M mobile/src/api/README.md
 M mobile/src/components/CLAUDE.md
 M mobile/src/components/README.md
 M mobile/src/hooks/README.md
 M mobile/src/navigation/CLAUDE.md
 M mobile/src/navigation/README.md
 M mobile/src/screens/CLAUDE.md
 M mobile/src/screens/README.md
 M mobile/src/shared/README.md
 M mobile/src/state/CLAUDE.md
 M mobile/src/state/README.md
 M mobile/src/theme/README.md
 M mobile/src/utils/CLAUDE.md
 M mobile/src/utils/README.md
 M mockups/CLAUDE.md
 M qa/CLAUDE.md
 M qa/README.md
 M docs/research/competitors/capture-policy.md
 M screens/CLAUDE.md
 M screens/web/README.md
 M scripts/CLAUDE.md
 M scripts/README.md
 M web/CLAUDE.md
?? .claude/skills/README.md
?? .claude/skills/feedback/scripts/fetch_feedback.py
?? .github/CLAUDE.md
?? docs/plans/budget-scalability/review-2026-09-04.md
?? docs/plans/trade-engine-balance/history/engineering-brief.md
?? backend/outlook/CLAUDE.md
?? backend/tests/CLAUDE.md
?? scripts/codecity/README.md
?? scripts/codecity/generate.py
?? scripts/codecity/index.html
?? dd.json
?? docs/design/brand/fleeced-logo-sheet.png
?? docs/feedback/items/304-positional-need-filter/batch-plan.md
?? docs/feedback/items/304-positional-need-filter/hld-delta.md
?? docs/feedback/items/304-positional-need-filter/lld-delta.md
?? docs/feedback/items/304-positional-need-filter/plan.md
?? docs/feedback/items/304-positional-need-filter/prd.md
?? docs/feedback/items/304-positional-need-filter/reconciliation-log.md
?? docs/feedback/items/304-positional-need-filter/review-round-1.md
?? docs/feedback/items/304-positional-need-filter/scope.md
?? docs/feedback/items/304-positional-need-filter/status.md
?? docs/feedback/items/321-espn-token-bleed/plan.md
?? docs/feedback/items/321-espn-token-bleed/prd.md
?? docs/feedback/items/321-espn-token-bleed/reconciliation-log.md
?? docs/feedback/items/321-espn-token-bleed/review-round-1.md
?? docs/feedback/items/321-espn-token-bleed/scope.md
?? docs/feedback/items/321-espn-token-bleed/status.md
?? docs/feedback/items/322-mock-draft-room-ui/plan.md
?? docs/feedback/items/322-mock-draft-room-ui/prd.md
?? docs/feedback/items/322-mock-draft-room-ui/reconciliation-log.md
?? docs/feedback/items/322-mock-draft-room-ui/review-round-1.md
?? docs/feedback/items/322-mock-draft-room-ui/scope.md
?? docs/feedback/items/322-mock-draft-room-ui/status.md
?? docs/feedback/items/323-mock-draft-pick-labels/status.md
?? docs/feedback/items/324-mock-draft-picks-wrap/status.md
?? docs/feedback/items/325-mock-draft-ticker-height/status.md
?? docs/feedback/items/326-mock-draft-team-sheet/status.md
?? docs/feedback/items/327-mock-draft-pool-search/status.md
?? docs/feedback/items/328-mock-draft-pick-assignment/hld-delta.md
?? docs/feedback/items/328-mock-draft-pick-assignment/lld-delta.md
?? docs/feedback/items/328-mock-draft-pick-assignment/plan.md
?? docs/feedback/items/328-mock-draft-pick-assignment/prd.md
?? docs/feedback/items/328-mock-draft-pick-assignment/reconciliation-log.md
?? docs/feedback/items/328-mock-draft-pick-assignment/review-round-1.md
?? docs/feedback/items/328-mock-draft-pick-assignment/scope.md
?? docs/feedback/items/328-mock-draft-pick-assignment/status.md
?? docs/feedback/items/330-offer-prefill/plan.md
?? docs/feedback/items/330-offer-prefill/prd.md
?? docs/feedback/items/330-offer-prefill/reconciliation-log.md
?? docs/feedback/items/330-offer-prefill/review-round-1.md
?? docs/feedback/items/330-offer-prefill/scope.md
?? docs/feedback/items/330-offer-prefill/status.md
?? docs/feedback/items/331-player-cards-stats/stat-sources-research.md
?? docs/feedback/items/334-matches-dismiss-latency/plan.md
?? docs/feedback/items/334-matches-dismiss-latency/prd.md
?? docs/feedback/items/334-matches-dismiss-latency/reconciliation-log.md
?? docs/feedback/items/334-matches-dismiss-latency/review-round-1.md
?? docs/feedback/items/334-matches-dismiss-latency/scope.md
?? docs/feedback/items/334-matches-dismiss-latency/status.md
?? docs/feedback/items/335-matches-filter-counts/status.md
?? docs/feedback/items/336-exclude-actioned-trades/status.md
?? docs/feedback/items/339-pick-not-the-gap/status.md
?? docs/feedback/items/340-max-overpay-cap/status.md
?? docs/feedback/items/341-package-position-cap/status.md
?? docs/feedback/items/358-team-analysis/session-prompt.md
?? docs/plans/archive/2026/audit-p0-remediation/README.md
?? docs/plans/archive/2026/audit-p1-remediation/README.md
?? docs/plans/connected-rankings/build-v1-premium-import/scope.md
?? docs/plans/connected-rankings/plan-2026-08-15.md
?? docs/plans/connected-rankings/premium-rank-sets-addendum-2026-08-15.md
?? docs/plans/connected-rankings/reconciliation-log-2026-08-15.md
?? docs/plans/connected-rankings/research/2026-08-15-dlf.md
?? docs/plans/connected-rankings/research/2026-08-15-dynasty-nerds.md
?? docs/plans/connected-rankings/research/2026-08-15-etr.md
?? docs/plans/decline-reason-capture/SPEC.md
?? docs/plans/archive/2026/draft-extensions/README.md
?? docs/plans/dynasty-year-in-review/README.md
?? docs/plans/dynasty-year-in-review/review-data-architect-final.md
?? docs/plans/dynasty-year-in-review/review-data-architect-r1.md
?? docs/plans/dynasty-year-in-review/review-eng-architect-final.md
?? docs/plans/dynasty-year-in-review/review-eng-architect-r1.md
?? docs/plans/archive/2026/rookie-draft/README.md
?? docs/plans/settings-ia-hub/plan.md
?? docs/plans/settings-ia-hub/scope.md
?? docs/plans/three-model-bakeoff/PLAN.md
?? docs/plans/web-parity/plan.md
?? docs/recovery/2026-08-16-feedback-wave-sweep.md
?? docs/recovery/2026-08-16-worktree-sweep/README.md
?? docs/recovery/2026-08-16-worktree-sweep/patches/claude-awesome-northcutt-0a5093.patch
?? docs/recovery/2026-08-16-worktree-sweep/patches/claude-cranky-hofstadter-251429.patch
?? docs/recovery/2026-08-16-worktree-sweep/patches/claude-keen-varahamihira-8986d4.patch
?? docs/recovery/2026-08-16-worktree-sweep/patches/claude-magical-cerf-7cfaca.patch
?? docs/recovery/2026-08-16-worktree-sweep/patches/claude-magical-hofstadter-40cf12.patch
?? docs/recovery/2026-08-16-worktree-sweep/patches/claude-nifty-shtern-6dbae1.patch
?? docs/recovery/2026-08-16-worktree-sweep/patches/claude-pensive-kilby-d53555.patch
?? docs/recovery/2026-08-16-worktree-sweep/patches/feat-feedback-mobile-sync.patch
?? docs/recovery/2026-08-16-worktree-sweep/patches/worktree-agent-a064c586eb5fd3310.patch
?? docs/recovery/2026-08-16-worktree-sweep/patches/worktree-agent-ac919199823a00f48.patch
?? docs/reviews/2026/2026-08-16-p0-remediation-status.md
?? docs/reviews/2026/2026-08-18-trade-logic-archaeology.md
?? docs/reviews/2026/2026-08-18-valuation-age-audit.md
?? docs/reviews/2026/2026-08-19-web-parity-audit.md
?? fs.html
?? githooks/CLAUDE.md
?? mobile/scripts/README.md
?? mobile/tests/README.md
?? mockups/decline-reason-capture/01-post-pass-sheet.html
?? mockups/decline-reason-capture/02-reason-as-action.html
?? mockups/decline-reason-capture/03-two-question-microflow.html
?? mockups/decline-reason-capture/04-inline-chips.html
?? mockups/decline-reason-capture/05-sampled-quick-question.html
?? mockups/decline-reason-capture/06-copy-drafts.html
?? mockups/decline-reason-capture/07-two-step-diagnostic.html
?? mockups/decline-reason-capture/index.html
?? mockups/settings-ia-hub/index.html
?? mockups/standing-offer-362/README.md
?? mockups/standing-offer-362/index.html
?? reference/Untitled.rtfd/1f4f2.svg
?? reference/Untitled.rtfd/TXT.rtf
?? reference/dynasty-nerds-app/01-home-leagues.png
?? reference/dynasty-nerds-app/02-accounts.png
?? reference/dynasty-nerds-app/03-analyzer.png
?? reference/dynasty-nerds-app/03b-analyzer-schedule.png
?? reference/dynasty-nerds-app/03c-analyzer-transactions-comingsoon.png
?? reference/dynasty-nerds-app/04-rankings-sflex.png
?? reference/dynasty-nerds-app/04b-rankings-format-picker.png
?? reference/dynasty-nerds-app/04c-rankings-ppr-1qb.png
?? reference/dynasty-nerds-app/04d-rankings-settings-compare.png
?? reference/dynasty-nerds-app/05-player-detail-overview.png
?? reference/dynasty-nerds-app/05b-player-detail-articles.png
?? reference/dynasty-nerds-app/05c-player-detail-nerdscore.png
?? reference/dynasty-nerds-app/05d-player-detail-stats-leagues.png
?? reference/dynasty-nerds-app/06-shares.png
?? reference/dynasty-nerds-app/07-data-hub-empty.png
?? reference/dynasty-nerds-app/07b-data-hub-filtered.png
?? reference/dynasty-nerds-app/08-free-agents.png
?? reference/dynasty-nerds-app/09-rookies.png
?? reference/dynasty-nerds-app/10-trades-browser.png
?? reference/dynasty-nerds-app/10b-trades-browser-filter.png
?? reference/dynasty-nerds-app/11-team-calculator-empty.png
?? reference/dynasty-nerds-app/11b-team-calculator-filled.png
?? reference/dynasty-nerds-app/12-open-calculator-empty.png
?? reference/dynasty-nerds-app/12b-open-calculator-filled.png
?? reference/dynasty-nerds-app/13-drafts-mocks-list.png
?? reference/dynasty-nerds-app/13b-mock-draft-board.png
?? reference/dynasty-nerds-app/14-league-draft.png
?? reference/dynasty-nerds-app/15-settings.png
?? reference/dynasty-nerds-app/16-custom-ranks-list.png
?? reference/dynasty-nerds-app/16b-custom-ranks-editor.png
?? reference/dynasty-nerds-app/17-rank-sets-picker.png
?? reference/dynasty-nerds-app/18-league-search.png
?? reference/dynasty-nerds-app/index.md
?? qa/evidence/2026-08-13/smoke-01-signin.png
?? qa/evidence/2026-08-13/smoke-05-trades-render.png
?? qa/evidence/2026-08-13/smoke-08-matches.png
?? qa/evidence/2026-08-13/smoke-10-canary.png
?? qa/evidence/2026-08-13/smoke-11a-apple-signin-no-error.png
```

Ignored files/directories (names only; caches/dependencies are distinguishable from data and credentials):

```text
.DS_Store
.claude/worktrees/
.pytest_cache/
.pytest_cache/.gitignore
.pytest_cache/CACHEDIR.TAG
.pytest_cache/README.md
.pytest_cache/v/
__pycache__/
app-teardown-review/
archive/.DS_Store
archive/cleanup-2026-07-19/all-refs-2026-07-19.bundle
archive/skill-workspaces/feature-evaluator.skill
archive/skill-workspaces/project-architect.skill
archive/skill-workspaces/project-reorganizer-workspace/
archive/skill-workspaces/project-reorganizer.skill
backend/.DS_Store
backend/.pytest_cache/
backend/.pytest_cache/.gitignore
backend/.pytest_cache/CACHEDIR.TAG
backend/.pytest_cache/README.md
backend/.pytest_cache/v/
backend/__pycache__/
backend/eval/__pycache__/
backend/outlook/__pycache__/
backend/scripts/__pycache__/
backend/tests/__pycache__/
backend/tests/fixtures/__pycache__/
backend/tests/support/__pycache__/
backend/tools/__pycache__/
scripts/codecity/city-data.js
scripts/codecity/city-data.json
scripts/codecity/city.html
data/
docs/.DS_Store
docs/design/.DS_Store
docs/design/icon-explorations/
docs/references/
docs/references/.DS_Store
feedback-workspace/
feedback-workspace/126/
feedback-workspace/214/
feedback-workspace/board-backup/
feedback-workspace/deck-eval/
feedback-workspace/feedback-review-2026-08-08.html
feedback-workspace/swipe-harness/
feedback-workspace/tiktok-discovery/
mobile/.expo/
mobile/ios/.xcode.env.local
mobile/ios/DTFDynastyTradeFinder.xcodeproj/project.xcworkspace/
mobile/ios/Pods/
mobile/ios/build/
mobile/node_modules/
mobile/test-artifacts/
mockups/trade-calc/.expo/
mockups/trade-calc/node_modules/
qa/api/scratch/
qa/api/scratch_api2/
qa/api/scratch_cfg/
qa/db/scratch/
qa/e2e/scratch/
qa/e2e/scratch4/
qa/eng/scratch/
qa/lib/__pycache__/
qa/perf/scratch/
qa/sec/scratch/
qa/sec/scratch_int/
qa/sim-runs/
reference/.DS_Store
scripts/__pycache__/
scripts/scratch/
secrets.local.env
staged-work/
web/.DS_Store
```

Git administrative markers: none observed.

</details>

<details><summary>/private/tmp/claude-501/-Users-teresadickens-Documents-Claude-Projects-Fantasy-Trade-Finder--claude-worktrees-happy-golick-345cf1/f75cd725-9d48-417e-a928-f0ff331ef022/scratchpad/wt-417 — full local-state filenames</summary>

Tracked/untracked status:

```text
Directory missing; status cannot be inspected.
```

Ignored files/directories (names only; caches/dependencies are distinguishable from data and credentials):

```text
None observed.
```

Git administrative markers: none observed.

</details>

<details><summary>/private/tmp/claude-501/-Users-teresadickens-Documents-Claude-Projects-Fantasy-Trade-Finder--claude-worktrees-happy-golick-345cf1/f75cd725-9d48-417e-a928-f0ff331ef022/scratchpad/wt-d178 — full local-state filenames</summary>

Tracked/untracked status:

```text
Directory missing; status cannot be inspected.
```

Ignored files/directories (names only; caches/dependencies are distinguishable from data and credentials):

```text
None observed.
```

Git administrative markers: none observed.

</details>

<details><summary>/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/agent-a36aaf8ad623b3be3 — full local-state filenames</summary>

Tracked/untracked status:

```text
 M mobile/ios/Podfile.lock
```

Ignored files/directories (names only; caches/dependencies are distinguishable from data and credentials):

```text
.pytest_cache/
.pytest_cache/.gitignore
.pytest_cache/CACHEDIR.TAG
.pytest_cache/README.md
.pytest_cache/v/
backend/__pycache__/
backend/eval/__pycache__/
backend/outlook/__pycache__/
backend/tests/__pycache__/
backend/tests/fixtures/__pycache__/
backend/tests/support/__pycache__/
data/
mobile/.expo/
mobile/ios/.xcode.env.local
mobile/ios/Pods/
mobile/ios/build/
mobile/node_modules/
mobile/scripts/
```

Git administrative markers: none observed.

</details>

<details><summary>/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/agent-ac3579d0fd8f1d2d8 — full local-state filenames</summary>

Tracked/untracked status:

```text
 M mobile/package-lock.json
```

Ignored files/directories (names only; caches/dependencies are distinguishable from data and credentials):

```text
mobile/node_modules/
```

Git administrative markers: none observed.

</details>

<details><summary>/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/agent-ae3050bc4e4ca4e49 — full local-state filenames</summary>

Tracked/untracked status:

```text
?? mobile/node_modules
```

Ignored files/directories (names only; caches/dependencies are distinguishable from data and credentials):

```text
None observed.
```

Git administrative markers: none observed.

</details>

<details><summary>/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/app-launch-scorecard-356d64 — full local-state filenames</summary>

Tracked/untracked status:

```text
 M docs/plans/monetization/README.md
?? docs/business/product/2026-08-27-launch-monetization-scorecard.md
?? docs/business/product/2026-08-27-monetization-timing-research.md
?? docs/plans/monetization/iap-enablement-runbook-2026-08-27.md
?? docs/plans/trade-model-review/plan-2026-08-27.md
```

Ignored files/directories (names only; caches/dependencies are distinguishable from data and credentials):

```text
None observed.
```

Git administrative markers: none observed.

</details>

<details><summary>/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/compassionate-jones-ea8a0e — full local-state filenames</summary>

Tracked/untracked status:

```text
Clean.
```

Ignored files/directories (names only; caches/dependencies are distinguishable from data and credentials):

```text
.pytest_cache/
.pytest_cache/.gitignore
.pytest_cache/CACHEDIR.TAG
.pytest_cache/README.md
.pytest_cache/v/
backend/__pycache__/
backend/eval/__pycache__/
backend/outlook/__pycache__/
backend/scripts/__pycache__/
backend/tests/__pycache__/
backend/tests/fixtures/__pycache__/
backend/tests/support/__pycache__/
data/
docs/plans/consensus-fit-sort-key/__pycache__/
scripts/__pycache__/
```

Git administrative markers: none observed.

</details>

<details><summary>/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/gracious-knuth-62ebbe — full local-state filenames</summary>

Tracked/untracked status:

```text
 M backend/data_loader.py
 M backend/dp_values_history.py
 M backend/tests/test_dp_crosswalk_position.py
 M backend/tests/test_dp_values_history.py
 M docs/feedback/items/169-outlook-league-summary/dated-values-revalidation-2026-08-09.md
 M docs/integrations/dynastyprocess.md
 M living-memory/TEST_LEDGER.md
?? .claude/skills/feedback/scripts/fetch_feedback.py
```

Ignored files/directories (names only; caches/dependencies are distinguishable from data and credentials):

```text
.pytest_cache/
.pytest_cache/.gitignore
.pytest_cache/CACHEDIR.TAG
.pytest_cache/README.md
.pytest_cache/v/
backend/__pycache__/
backend/eval/__pycache__/
backend/outlook/__pycache__/
backend/tests/__pycache__/
backend/tests/fixtures/__pycache__/
backend/tests/support/__pycache__/
data/
scripts/__pycache__/
```

Git administrative markers: none observed.

</details>

<details><summary>/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/happy-golick-345cf1 — full local-state filenames</summary>

Tracked/untracked status:

```text
Clean.
```

Ignored files/directories (names only; caches/dependencies are distinguishable from data and credentials):

```text
.pytest_cache/
.pytest_cache/.gitignore
.pytest_cache/CACHEDIR.TAG
.pytest_cache/README.md
.pytest_cache/v/
backend/__pycache__/
backend/eval/__pycache__/
backend/outlook/__pycache__/
backend/scripts/__pycache__/
backend/tests/__pycache__/
backend/tests/fixtures/__pycache__/
backend/tests/support/__pycache__/
data/
docs/plans/consensus-fit-sort-key/__pycache__/
mobile/node_modules/
scripts/__pycache__/
secrets.local.env
```

Git administrative markers: none observed.

</details>

<details><summary>/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/jolly-leakey-d20295 — full local-state filenames</summary>

Tracked/untracked status:

```text
 M backend/tests/CLAUDE.md
```

Ignored files/directories (names only; caches/dependencies are distinguishable from data and credentials):

```text
.pytest_cache/
.pytest_cache/.gitignore
.pytest_cache/CACHEDIR.TAG
.pytest_cache/README.md
.pytest_cache/v/
backend/__pycache__/
backend/eval/__pycache__/
backend/outlook/__pycache__/
backend/tests/__pycache__/
backend/tests/fixtures/__pycache__/
backend/tests/support/__pycache__/
data/
mobile/node_modules/
scripts/__pycache__/
```

Git administrative markers: none observed.

</details>

<details><summary>/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/modest-albattani-138a2d — full local-state filenames</summary>

Tracked/untracked status:

```text
 M docs/design/components.md
 M docs/plans/archive/2026/mobile-testing/lld.md
 M living-memory/CHANGELOG.md
 M living-memory/DECISIONS.md
 M living-memory/HANDOFF.md
 M living-memory/LLD.md
 M living-memory/TEST_LEDGER.md
 M mobile/package.json
 M mobile/src/navigation/CLAUDE.md
 M mobile/src/navigation/RootNav.tsx
 M mobile/tests/README.md
?? docs/plans/modal-close-controls/code-walk.md
?? docs/plans/modal-close-controls/scope.md
?? docs/plans/modal-close-controls/testflight-checklist.md
?? mobile/tests/check-modal-close-controls.js
```

Ignored files/directories (names only; caches/dependencies are distinguishable from data and credentials):

```text
.pytest_cache/
.pytest_cache/.gitignore
.pytest_cache/CACHEDIR.TAG
.pytest_cache/README.md
.pytest_cache/v/
backend/__pycache__/
backend/eval/__pycache__/
backend/outlook/__pycache__/
backend/tests/__pycache__/
backend/tests/fixtures/__pycache__/
backend/tests/support/__pycache__/
data/
mobile/node_modules/
scripts/__pycache__/
```

Git administrative markers: none observed.

</details>

<details><summary>/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/modest-cerf-12ce88 — full local-state filenames</summary>

Tracked/untracked status:

```text
?? .claude/skills/feedback/scripts/fetch_feedback.py
```

Ignored files/directories (names only; caches/dependencies are distinguishable from data and credentials):

```text
.pytest_cache/
.pytest_cache/.gitignore
.pytest_cache/CACHEDIR.TAG
.pytest_cache/README.md
.pytest_cache/v/
backend/__pycache__/
backend/eval/__pycache__/
backend/outlook/__pycache__/
backend/tests/__pycache__/
backend/tests/fixtures/__pycache__/
backend/tests/support/__pycache__/
data/
scripts/__pycache__/
```

Git administrative markers: none observed.

</details>

<details><summary>/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/monetization-features-feedback-a6fe77 — full local-state filenames</summary>

Tracked/untracked status:

```text
 M backend/database.py
 M backend/feature_flags.py
 M backend/server.py
 M backend/tests/fixtures/flags/onboarding-v2.json
 M backend/tests/fixtures/flags/profiles-on.json
 M backend/tests/fixtures/flags/release.json
 M backend/tests/test_bakeoff_arm_a_golden.py
 M backend/tests/test_bakeoff_serving.py
 M backend/trade_gen_v2.py
 M backend/trade_optimizer.py
 M backend/trade_service.py
 M config/features.json
 M docs/plans/three-model-bakeoff/scope-phase2.md
?? backend/tests/test_trade_policy.py
?? backend/trade_policy.py
?? docs/plans/personal-market-policy/scope.md
```

Ignored files/directories (names only; caches/dependencies are distinguishable from data and credentials):

```text
.pytest_cache/
.pytest_cache/.gitignore
.pytest_cache/CACHEDIR.TAG
.pytest_cache/README.md
.pytest_cache/v/
backend/__pycache__/
backend/eval/__pycache__/
backend/outlook/__pycache__/
backend/scripts/__pycache__/
backend/tests/__pycache__/
backend/tests/fixtures/__pycache__/
backend/tests/support/__pycache__/
data/
docs/plans/consensus-fit-sort-key/__pycache__/
mobile/node_modules/
scripts/__pycache__/
```

Git administrative markers: none observed.

</details>

<details><summary>/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/new-user-feedback-5fa613 — full local-state filenames</summary>

Tracked/untracked status:

```text
Clean.
```

Ignored files/directories (names only; caches/dependencies are distinguishable from data and credentials):

```text
.pytest_cache/
.pytest_cache/.gitignore
.pytest_cache/CACHEDIR.TAG
.pytest_cache/README.md
.pytest_cache/v/
backend/__pycache__/
backend/eval/__pycache__/
backend/outlook/__pycache__/
backend/scripts/__pycache__/
backend/tests/__pycache__/
backend/tests/fixtures/__pycache__/
backend/tests/support/__pycache__/
data/
docs/plans/consensus-fit-sort-key/__pycache__/
mobile/node_modules/
scripts/__pycache__/
secrets.local.env
```

Git administrative markers: none observed.

</details>

<details><summary>/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/open-feedback-summary-b43796 — full local-state filenames</summary>

Tracked/untracked status:

```text
Clean.
```

Ignored files/directories (names only; caches/dependencies are distinguishable from data and credentials):

```text
backend/__pycache__/
data/
```

Git administrative markers: none observed.

</details>

<details><summary>/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/sad-benz-9922d6 — full local-state filenames</summary>

Tracked/untracked status:

```text
 M backend/server.py
 M backend/tests/test_espn_link_route.py
 M docs/api-reference.md
 M docs/data-dictionary.md
 M docs/integrations/espn.md
 M living-memory/DECISIONS.md
 M living-memory/HANDOFF.md
 M living-memory/TEST_LEDGER.md
```

Ignored files/directories (names only; caches/dependencies are distinguishable from data and credentials):

```text
.pytest_cache/
.pytest_cache/.gitignore
.pytest_cache/CACHEDIR.TAG
.pytest_cache/README.md
.pytest_cache/v/
backend/__pycache__/
backend/tests/__pycache__/
data/
```

Git administrative markers: none observed.

</details>

<details><summary>/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/team-outlook-experience-27a7a1 — full local-state filenames</summary>

Tracked/untracked status:

```text
 M mockups/CLAUDE.md
?? mockups/team-review-filters-2026-08-20/README.md
?? mockups/team-review-filters-2026-08-20/index.html
```

Ignored files/directories (names only; caches/dependencies are distinguishable from data and credentials):

```text
.pytest_cache/
.pytest_cache/.gitignore
.pytest_cache/CACHEDIR.TAG
.pytest_cache/README.md
.pytest_cache/v/
backend/__pycache__/
backend/eval/__pycache__/
backend/outlook/__pycache__/
backend/tests/__pycache__/
backend/tests/fixtures/__pycache__/
backend/tests/support/__pycache__/
data/
mobile/node_modules
scripts/__pycache__/
```

Git administrative markers: none observed.

</details>

<details><summary>/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/trade-model-review-101bf7 — full local-state filenames</summary>

Tracked/untracked status:

```text
Clean.
```

Ignored files/directories (names only; caches/dependencies are distinguishable from data and credentials):

```text
.pytest_cache/
.pytest_cache/.gitignore
.pytest_cache/CACHEDIR.TAG
.pytest_cache/README.md
.pytest_cache/v/
backend/__pycache__/
backend/eval/__pycache__/
backend/outlook/__pycache__/
backend/scripts/__pycache__/
backend/tests/__pycache__/
backend/tests/fixtures/__pycache__/
backend/tests/support/__pycache__/
data/
docs/plans/consensus-fit-sort-key/__pycache__/
scripts/__pycache__/
```

Git administrative markers: none observed.

</details>

<details><summary>/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/unruffled-meitner-3596cb — full local-state filenames</summary>

Tracked/untracked status:

```text
Clean.
```

Ignored files/directories (names only; caches/dependencies are distinguishable from data and credentials):

```text
.pytest_cache/
.pytest_cache/.gitignore
.pytest_cache/CACHEDIR.TAG
.pytest_cache/README.md
.pytest_cache/v/
backend/__pycache__/
backend/eval/__pycache__/
backend/outlook/__pycache__/
backend/scripts/__pycache__/
backend/tests/__pycache__/
backend/tests/fixtures/__pycache__/
backend/tests/support/__pycache__/
data/
docs/plans/consensus-fit-sort-key/__pycache__/
mobile/node_modules/
scripts/__pycache__/
secrets.local.env
```

Git administrative markers: none observed.

</details>

<details><summary>/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/vibrant-allen-023c8f — full local-state filenames</summary>

Tracked/untracked status:

```text
 M living-memory/GOTCHAS.md
 M living-memory/NEXT.md
```

Ignored files/directories (names only; caches/dependencies are distinguishable from data and credentials):

```text
backend/__pycache__/
data/
```

Git administrative markers: none observed.

</details>

<details><summary>/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/vigorous-chaum-272d92 — full local-state filenames</summary>

Tracked/untracked status:

```text
 M living-memory/DECISIONS.md
 M living-memory/GOTCHAS.md
 M living-memory/HANDOFF.md
 M living-memory/OPEN_QUESTIONS.md
 M archive/retired-tooling/mobile/maestro/capture/anchors.yaml
 M archive/retired-tooling/mobile/maestro/capture/calc.yaml
 M archive/retired-tooling/mobile/maestro/capture/draft-room@draft.yaml
 M archive/retired-tooling/mobile/maestro/capture/free-agents.yaml
 M archive/retired-tooling/mobile/maestro/capture/league-summary.yaml
 M archive/retired-tooling/mobile/maestro/capture/league-summary@single-format.yaml
 M archive/retired-tooling/mobile/maestro/capture/league.yaml
 M archive/retired-tooling/mobile/maestro/capture/league@espn.yaml
 M archive/retired-tooling/mobile/maestro/capture/league@near-unlock.yaml
 M archive/retired-tooling/mobile/maestro/capture/league@quickset-done.yaml
 M archive/retired-tooling/mobile/maestro/capture/league@single-format.yaml
 M archive/retired-tooling/mobile/maestro/capture/league@two-leagues.yaml
 M archive/retired-tooling/mobile/maestro/capture/manual-ranks.yaml
 M archive/retired-tooling/mobile/maestro/capture/manual-ranks@fresh.yaml
 M archive/retired-tooling/mobile/maestro/capture/matches.yaml
 M archive/retired-tooling/mobile/maestro/capture/matches@espn.yaml
 M archive/retired-tooling/mobile/maestro/capture/matches@fresh.yaml
 M archive/retired-tooling/mobile/maestro/capture/matches@near-unlock.yaml
 M archive/retired-tooling/mobile/maestro/capture/matches@two-leagues.yaml
 M archive/retired-tooling/mobile/maestro/capture/mock-draft@draft-pre.yaml
 M archive/retired-tooling/mobile/maestro/capture/mock-draft@draft.yaml
 M archive/retired-tooling/mobile/maestro/capture/onboarding-leaguepicker@two-leagues.yaml
 M archive/retired-tooling/mobile/maestro/capture/onboarding-signin@fresh.yaml
 M archive/retired-tooling/mobile/maestro/capture/onboarding-tour@fresh.yaml
 M archive/retired-tooling/mobile/maestro/capture/pick-assignment@espn.yaml
 M archive/retired-tooling/mobile/maestro/capture/portfolio.yaml
 M archive/retired-tooling/mobile/maestro/capture/portfolio@two-leagues.yaml
 M archive/retired-tooling/mobile/maestro/capture/quick-rank.yaml
 M archive/retired-tooling/mobile/maestro/capture/quick-set.yaml
 M archive/retired-tooling/mobile/maestro/capture/rank-home.yaml
 M archive/retired-tooling/mobile/maestro/capture/record-picks@espn.yaml
 M archive/retired-tooling/mobile/maestro/capture/rookie-ranks@draft.yaml
 M archive/retired-tooling/mobile/maestro/capture/sheets/sheets-rank-menu.yaml
 M archive/retired-tooling/mobile/maestro/capture/sheets/sheets-trade-dna.yaml
 M archive/retired-tooling/mobile/maestro/capture/tiers.yaml
 M archive/retired-tooling/mobile/maestro/capture/tiers@fresh.yaml
 M archive/retired-tooling/mobile/maestro/capture/trades.yaml
 M archive/retired-tooling/mobile/maestro/capture/trades@fresh.yaml
 M archive/retired-tooling/mobile/maestro/capture/trades@single-format.yaml
 M archive/retired-tooling/mobile/maestro/capture/trends.yaml
 M archive/retired-tooling/mobile/maestro/capture/trends@fresh.yaml
 M archive/retired-tooling/mobile/maestro/capture/trios.yaml
 M archive/retired-tooling/mobile/maestro/capture/trios@fresh.yaml
 M archive/retired-tooling/mobile/maestro/capture/trios@near-unlock.yaml
 M screens/CLAUDE.md
 M screens/manifest.json
```

Ignored files/directories (names only; caches/dependencies are distinguishable from data and credentials):

```text
None observed.
```

Git administrative markers: none observed.

</details>

<details><summary>/Users/teresadickens/Documents/Claude/Projects/ftf-p1-remediation — full local-state filenames</summary>

Tracked/untracked status:

```text
Clean.
```

Ignored files/directories (names only; caches/dependencies are distinguishable from data and credentials):

```text
.pytest_cache/
.pytest_cache/.gitignore
.pytest_cache/CACHEDIR.TAG
.pytest_cache/README.md
.pytest_cache/v/
backend/__pycache__/
backend/eval/__pycache__/
backend/outlook/__pycache__/
backend/tests/__pycache__/
backend/tests/fixtures/__pycache__/
backend/tests/support/__pycache__/
data/
mobile/node_modules/
scripts/__pycache__/
```

Git administrative markers: none observed.

</details>

<details><summary>/Users/teresadickens/Documents/Claude/Projects/ftf-render-cron-migration — full local-state filenames</summary>

Tracked/untracked status:

```text
Clean.
```

Ignored files/directories (names only; caches/dependencies are distinguishable from data and credentials):

```text
None observed.
```

Git administrative markers: none observed.

</details>

<details><summary>/private/tmp/ftf-security-hardening-20260904 — full local-state filenames</summary>

Tracked/untracked status:

```text
 M backend/accounts.py
 M backend/analytics_ingest.py
 M backend/database.py
 M backend/server.py
 M backend/tests/test_account_data_rights.py
 M backend/tests/test_account_first.py
 M backend/tests/test_co_owner_rosters.py
 M backend/tests/test_verified_reads.py
 M backend/tests/test_verified_sessions.py
 M docs/plans/README.md
 M mobile/src/api/auth.ts
?? backend/session_input.py
?? backend/tests/test_account_deletion_coverage.py
?? backend/tests/test_identity_binding_security.py
?? backend/tests/test_private_session_ownership.py
?? backend/tests/test_session_input_security.py
?? docs/plans/archive/2026/security-data-hardening/scope.md
?? scripts/remediate_analytics_tokens.py
```

Ignored files/directories (names only; caches/dependencies are distinguishable from data and credentials):

```text
.pytest_cache/
.pytest_cache/.gitignore
.pytest_cache/CACHEDIR.TAG
.pytest_cache/README.md
.pytest_cache/v/
backend/__pycache__/
backend/tests/__pycache__/
data/
```

Git administrative markers: none observed.

</details>

## Complete local branch inventory and pre-deletion tip ledger

Every local ref in the complete snapshot appears once. Upstream A/B is relative to its configured upstream (not main); a blank upstream means none configured. This table is recovery evidence, not a substitute for the dated pre-deletion ledger. Restore any retained object with `git branch <branch-name> <full-tip-sha>`.

| Branch | Tip SHA | Commit date | Upstream; upstream A/B | Main A/B | Verdict | Content evidence |
|---|---|---|---|---|---|---|
| `agent-12-consolidate-skip-button` | `a5bbff1f293ba39a38e1ac5c605625ba3a26c086` | 2026-04-29T15:23:43-04:00 | none; n/a | 1/1079 | HOLD unresolved content | E5 1 unmatched commits; 2/2 branch-touched paths differ |
| `agent-16-league-switcher` | `087e877f6aaa2688ac2b41a96d970ee5b2ec27b1` | 2026-04-27T20:38:31-04:00 | none; n/a | 1/1083 | SAFE branch cleanup | E4 main d76170663ff3d9a2a5d14ab99e9e58f49a8e6dca; patch abe280a9d6d011b5c6e3d54fa1d6861dbde45356 |
| `audit/armb-claims-1-2` | `45a2520c36778771190ba3e6cf34e96cc6bbaf41` | 2026-08-19T14:58:25-04:00 | none; n/a | 0/206 | SAFE branch cleanup | E1 tree d5041043ecb4876368c3fe846633ce0ecf08d45c |
| `audit/armb-claims-3-4` | `b2e794f94ba1f0dc37105e09d3ba61289f7d286d` | 2026-08-19T15:04:38-04:00 | none; n/a | 0/206 | SAFE branch cleanup | E1 tree 48b597ff2336ae5e16fe220bc158567b4265ff30 |
| `audit/armb-claims-5-6` | `238cc3ee0963175f257d681cb1dfdd2000162ff3` | 2026-08-19T14:59:04-04:00 | none; n/a | 0/206 | SAFE branch cleanup | E1 tree 0d499b1381a9987761c3ce89ef1c52d7045cfe59 |
| `audit/armb-remedy-bucket-a` | `d6b324194f7efad0878237bf6d0fa1133186eb00` | 2026-08-19T15:27:48-04:00 | refs/remotes/origin/main; 0/205 | 0/205 | SAFE branch cleanup | E1 tree 8a87d95231fd106135ae0f0b64d2d5d7af0fd8ac |
| `audit/armb-remedy-bucket-b` | `79f7cc3ebdd994e9c8def2980574ff316becdfaf` | 2026-08-19T15:22:35-04:00 | refs/remotes/origin/main; 0/205 | 0/205 | SAFE branch cleanup | E1 tree b2d84bd2a83d1e52c9a6cd20d7d1a53bee06c11b |
| `audit/armb-remedy-bucket-c` | `e873966e474746d127e41fb70c4a52da63e33582` | 2026-08-19T15:23:14-04:00 | refs/remotes/origin/main; 0/205 | 0/205 | SAFE branch cleanup | E1 tree 27656d726de5c258c2ed1c27bfcd1849bec93a63 |
| `audit/claim-7-armb` | `7cb9a25b6809770d8d08406773d9cc1572cb5d2f` | 2026-08-19T14:58:05-04:00 | none; n/a | 0/206 | SAFE branch cleanup | E1 tree 3d1213c37a561ffbb26544d7f3754214956b5c4b |
| `audit/consensus-gate-matrix` | `9026da7702fcf4fc117c903c92dddd6f7c226cfa` | 2026-08-19T17:14:56-04:00 | refs/remotes/origin/main; 0/205 | 0/205 | SAFE branch cleanup | E1 tree 2500b47ac089e6634fc2c134742166c549efdeeb |
| `audit/knockout-waterfall` | `307b8f8e120e60b912d6eed7d21dbef32595821a` | 2026-08-19T19:32:59-04:00 | refs/remotes/origin/main; 0/188 | 0/188 | SAFE branch cleanup | E1 tree a9225385b6c58967c0e475be08083cf4859f40d2 |
| `audit/knockout-waterfall-v2` | `290b3ed94d65df782fd9bd1f805b7a343651a531` | 2026-08-22T11:25:20-04:00 | none; n/a | 1/107 | HOLD unresolved content | E5 1 unmatched commits; 2/2 branch-touched paths differ |
| `audit/perf-optimization` | `71ed60b2edf1e88a6e64a99ad6e09ddfb2cddf34` | 2026-06-07T12:22:11-04:00 | refs/remotes/origin/audit/perf-optimization; 0/0 | 1/1030 | HOLD unresolved content | E5 1 unmatched commits; 40/44 branch-touched paths differ |
| `build-staging` | `63d2965d9d569f57aa4c480c5568239e6efb6cbd` | 2026-08-20T20:27:11-04:00 | refs/remotes/origin/main; 0/135 | 0/135 | SAFE branch cleanup | E1 tree 40142c7dfab3412b4c9b5c00e6b57caf19dd9940 |
| `chalkline-primitives` | `794c296551d926df63c97ba352c93f316e8ea263` | 2026-07-03T23:25:26-04:00 | none; n/a | 1/981 | HOLD unresolved content | E5 1 unmatched commits; 30/30 branch-touched paths differ |
| `chore/bakeoff-serve-interleaved` | `02e27dda7446dcf5289c2168776694d86d73395a` | 2026-08-19T00:05:15-04:00 | none; n/a | 0/246 | SAFE branch cleanup | E1 tree 8692ad580f42b335efdc5bc9ebf2af8b11a573bf |
| `chore/breaker-calibration-boundary-pin` | `739b8da416bb5930f5b467a8f9b449397c9a47f6` | 2026-08-21T12:54:18-04:00 | refs/remotes/origin/chore/breaker-calibration-boundary-pin; gone | 1/120 | SAFE branch cleanup | E3 1 changed paths equal current main |
| `chore/breaker-sweep-ledger` | `76c24247004c39afc0ee84747056e8b3d2edf393` | 2026-08-21T12:30:14-04:00 | refs/remotes/origin/chore/breaker-sweep-ledger; gone | 1/123 | SAFE branch cleanup | E3 1 changed paths equal current main |
| `chore/commit-docs-and-claude-tree` | `e00940d8c4ce36be2d082f985c76c99bb2c49e11` | 2026-05-21T10:18:26-04:00 | refs/remotes/origin/chore/commit-docs-and-claude-tree; 0/0 | 1/1048 | SAFE branch cleanup | E4 main 56fcf91d79623087f1a4cfefecc11759cef3cec8; patch 6757bf3d0530628f05e1e8653cb7de38eeae4f2e |
| `chore/eas-submit-ascappid` | `8353ec3075826d6db89efbf4231e86d137450959` | 2026-05-20T20:22:26-04:00 | refs/remotes/origin/chore/eas-submit-ascappid; 0/0 | 1/1051 | SAFE branch cleanup | E3 1 changed paths equal current main |
| `chore/session-wrapup` | `4340b60473bc1ab6d39fd80f3d312ad4a6e8c778` | 2026-08-20T21:24:57-04:00 | refs/remotes/origin/chore/session-wrapup; 0/0 | 0/127 | SAFE branch cleanup | E1 tree 697c439818ceb3faf6cfb55b727904a5d690409e |
| `claude/372-window-composite` | `ba4a6ad1446acddbac468d94e52faf38036b46c8` | 2026-08-20T20:58:25-04:00 | none; n/a | 0/136 | SAFE branch cleanup | E1 tree f6320ae6ce12803d0ebff47db9385319881c66bd |
| `claude/agitated-sanderson-d9eaf9` | `eb9c1dee7029a301d4bda535f12b380b8f80ddbc` | 2026-08-21T01:58:56-04:00 | none; n/a | 0/124 | SAFE branch cleanup | E1 tree 23391a2d0d7d5655e703015b0ccc8708198271c2 |
| `claude/api-audit-redundancies-9a6075` | `b8c8dd598e5d5302b240a4fc3e78b9265bd76ede` | 2026-09-03T12:19:36-04:00 | refs/remotes/origin/claude/api-audit-redundancies-9a6075; 0/0 | 12/5 | SAFE branch cleanup | E4 main c2775fe03fcd6d47824e17fa444681b0cc3628c0; patch e8684e5ac6949c9dbb5f801ec8663330cb4cded3 |
| `claude/app-entry-platform-options-3e16ac` | `4f8c05073a1fc2b5bbb1bdd02dab89f7e8cfee4d` | 2026-08-26T09:39:19-04:00 | refs/remotes/origin/claude/app-entry-platform-options-3e16ac; gone | 1/66 | SAFE branch cleanup | E4 main 20ac27f3da0e366ad11a0bb26abab4fdf7e2efbc; patch bc9fbe2005de08856260089d2ffb9399c7cc1861 |
| `claude/app-launch-scorecard-356d64` | `69dc0cae7db1cd41a522dfb7d33f280038d318c2` | 2026-08-27T11:41:54-04:00 | none; n/a | 0/53 | HOLD dirty worktree | E1 tree db1666864f5e59b3a8cd9bf31ccbc759c7e97e88 |
| `claude/awesome-northcutt-0a5093` | `968d9a8e13a3ba9d730bb542498f5b8d4aea299f` | 2026-07-17T17:48:15-04:00 | none; n/a | 0/909 | SAFE branch cleanup | E1 tree 431ef729f1cf5002b5032e54de63258eebc68ad5 |
| `claude/beautiful-saha-65d7fb` | `7dfcd168d5e7fe0609e2533d779a691c41e09a43` | 2026-08-12T22:27:03-04:00 | none; n/a | 0/425 | HOLD dirty worktree | E1 tree af9dab764ef855cc423390e1c9a0fc53cb56cc4f |
| `claude/busy-cohen-7530c5` | `0a924974a990b96ec7ba98d8a1bfa45ddb430c1d` | 2026-05-22T12:54:54-04:00 | none; n/a | 1/1036 | SAFE branch cleanup | E4 main eedcd2444808213374e62c83b70d7de8eccded3f; patch a1091f12dada9add1c9766c85e072fe813c0d25a |
| `claude/busy-hodgkin-b23fda` | `0a924974a990b96ec7ba98d8a1bfa45ddb430c1d` | 2026-05-22T12:54:54-04:00 | refs/remotes/origin/fix/tiers-drop-coord-space; 0/0 | 1/1036 | SAFE branch cleanup | E4 main eedcd2444808213374e62c83b70d7de8eccded3f; patch a1091f12dada9add1c9766c85e072fe813c0d25a |
| `claude/busy-swartz-521ff5` | `18f15f7ad36ca988ef364fc4d0041218f7313a52` | 2026-07-10T02:58:13-04:00 | refs/remotes/origin/claude/busy-swartz-521ff5; 0/0 | 0/997 | SAFE branch cleanup | E1 tree 544630af4d5d18e72ee6fb412f4e192e49eb6b5e |
| `claude/ci-check-js-doc-fix` | `b67d7b3a8e59c6d7b7d959151566cb7c14a1d0e4` | 2026-08-27T09:09:34-04:00 | refs/remotes/origin/main; 1/55 | 1/55 | HOLD unresolved content | E5 1 unmatched commits; 6/6 branch-touched paths differ |
| `claude/ci-gotchas` | `ad96131861d96a7486a941227781baecc1b10453` | 2026-08-15T14:36:00-04:00 | refs/remotes/origin/claude/ci-gotchas; gone | 1/375 | SAFE branch cleanup | E4 main ae6b9be52d547e38a0ef9941d7352bd42c5305d6; patch 22754c65c8848cd397f896b7539615261355344d |
| `claude/clever-euler-49a334` | `0edc7de7351a30fe0d4b8ee3068df31874bcda2d` | 2026-07-04T23:01:12-04:00 | none; n/a | 0/998 | SAFE branch cleanup | E1 tree 47f7616f0c5f1fac6ab0828533e1bfd09691fce5 |
| `claude/clever-pike-c7ecb9` | `8b7689a0f3a060f9b826079e65e4bc0b1f7e19d4` | 2026-08-19T00:39:08-04:00 | none; n/a | 0/245 | HOLD dirty worktree | E1 tree ce756d3692f885439eaf53f65c6ad8086001f367 |
| `claude/compassionate-goldstine-410636` | `49cf21e5002ac77ea5978ba17431b4671c5ebcfc` | 2026-04-19T18:04:19-04:00 | refs/remotes/origin/main; 0/1095 | 0/1095 | SAFE branch cleanup | E1 tree 3213580b201a8b25de83a09f8e25dd243b1f90d4 |
| `claude/compassionate-wilbur-e00696` | `5472e7034f545d3af228f26799e21f81c993b9bb` | 2026-08-21T16:34:47-04:00 | none; n/a | 0/112 | HOLD dirty worktree | E1 tree 6f5908e27a219ffe6a0a9da1e8201e88f276536e |
| `claude/compressed-board-ship-record` | `bec25bbf1f08e9a1083a448e4c2a4892e55239cb` | 2026-08-15T14:26:13-04:00 | refs/remotes/origin/claude/compressed-board-ship-record; gone | 1/376 | SAFE branch cleanup | E4 main f8b51be7b8c3ba75db05d99904db0147af1dc881; patch 57b03b907bdb9fceae13e76473e68393f9c31302 |
| `claude/condescending-jemison-61ad0a` | `49cf21e5002ac77ea5978ba17431b4671c5ebcfc` | 2026-04-19T18:04:19-04:00 | refs/remotes/origin/main; 0/1095 | 0/1095 | SAFE branch cleanup | E1 tree 3213580b201a8b25de83a09f8e25dd243b1f90d4 |
| `claude/cool-hermann` | `37d74b2bd15174e35ebfa6381b97af14232e9389` | 2026-04-15T20:59:59-04:00 | refs/remotes/origin/main; 0/1128 | 0/1128 | SAFE branch cleanup | E1 tree f144614882ad3ee48bedec9549efa469704a698e |
| `claude/counterparty-breaker-plan` | `c265a8af0779b40486b04e9c16a3d3239bc8c748` | 2026-08-21T12:15:55-04:00 | refs/remotes/origin/claude/counterparty-breaker-plan; gone | 23/124 | SAFE branch cleanup | E4 main 15b13986a1936da15fd3f13092d8d8b3cbf61d95; patch c8cf5ac37bc4111c00b02d9e4d9f4c9a2a2b1b5d |
| `claude/cranky-hofstadter-251429` | `0ad2fe9bc1c9f7cd69daf58aa0fdaa5de2a70c02` | 2026-07-10T15:37:01-04:00 | none; n/a | 0/923 | SAFE branch cleanup | E1 tree 342c0543d82ce342d9d174c284f1666abdf71bd4 |
| `claude/crazy-noyce-6cdea0` | `bc340607b6f0a78e434cae2552f1ae31d94c4c52` | 2026-04-26T22:36:40-04:00 | refs/remotes/origin/main; 0/1093 | 0/1093 | SAFE branch cleanup | E1 tree 915d07973a538bebf3a7b495a448114ceb140665 |
| `claude/driver-setup-step-7-b50718` | `e92f95c16034101f1d1f925b6e90b27273d62d4a` | 2026-08-30T12:09:11-04:00 | none; n/a | 0/24 | SAFE branch cleanup | E1 tree f3f7a76ecf7a00bb007ba94bb67405bed373ec44 |
| `claude/dynasty-consensus-rankings-update-2b8b02` | `606e512cd87f692eced3b92ccadb4f0192ea3449` | 2026-09-03T14:18:19-04:00 | none; n/a | 0/0 | HOLD ignored local files | E1 tree ad663e32c2049ad5a46bdfaac38aa245d98b1aa6 |
| `claude/elastic-kapitsa-c75ce7` | `9e1a8be1a6612ef2e6b6be99ef96bf46b2d33f27` | 2026-08-21T22:10:21-04:00 | refs/remotes/origin/main; 0/108 | 0/108 | SAFE branch cleanup | E1 tree 9e498480763593fb8b3bd468ec30bbb9e705e9a0 |
| `claude/entry-platform-login-option` | `55f06384ed5e944b4e61fe1b8ce23057f9d952a7` | 2026-08-26T15:36:48-04:00 | refs/remotes/origin/claude/entry-platform-login-option; gone | 1/61 | SAFE branch cleanup | E4 main 8ea8177bc007256a9117a0d7a28c91a70d1b2d19; patch b952e26185e507c02f68926a8d844c2a548fd6b7 |
| `claude/events-tracked-per-user-1110f1` | `af91d6f8225d662110e67188adee1705ce219d64` | 2026-08-29T12:41:55-04:00 | none; n/a | 0/38 | HOLD dirty worktree | E1 tree c0e372099deb61582926514c624ebb2697cca560 |
| `claude/exciting-bardeen-3a477c` | `74cd664030ed2a3603a7d8a5f384e5fff7f3d836` | 2026-07-12T14:19:48-04:00 | none; n/a | 0/913 | SAFE branch cleanup | E1 tree c8cb24b20ee725e57a2fb52a4500abeb168f21f7 |
| `claude/festive-mccarthy-b10c3a` | `cfe930018ee5ca66d5d67d679e8155d266f5d869` | 2026-07-10T10:34:46-04:00 | none; n/a | 0/934 | SAFE branch cleanup | E1 tree 8156e9a8bfcc4f19012fd62bd5c6801e89c54d4d |
| `claude/finder-gap-analysis-writeback` | `3f5af51c3e496c48a958171425933177cf9f9691` | 2026-08-31T17:44:09-04:00 | refs/remotes/origin/claude/finder-gap-analysis-writeback; 0/0 | 1/22 | SAFE branch cleanup | E4 main 2ceff988b41268753546d284466f070e3d0c3bca; patch 308c271a368e077e5bcc920a42d7d36edbca21d4 |
| `claude/finished-unmerged-worktrees-48b67b` | `867c3baaee6c5a6a4de417d2892f8c4a35a4d9ee` | 2026-08-25T05:08:19-04:00 | none; n/a | 0/66 | SAFE branch cleanup | E1 tree aa4596dae9cdd8d874e7828a418aeb7fdc9b4e3c |
| `claude/fleeced-trade-engine-balance-c0c75d` | `606e512cd87f692eced3b92ccadb4f0192ea3449` | 2026-09-03T14:18:19-04:00 | none; n/a | 0/0 | HOLD dirty worktree | E1 tree ad663e32c2049ad5a46bdfaac38aa245d98b1aa6 |
| `claude/ftf-file-continuation-c9185e` | `af91d6f8225d662110e67188adee1705ce219d64` | 2026-08-29T12:41:55-04:00 | refs/remotes/origin/claude/ftf-file-continuation-c9185e; 14/3 | 0/38 | SAFE branch cleanup | E1 tree c0e372099deb61582926514c624ebb2697cca560 |
| `claude/gifted-sanderson-0d3ca0` | `c321958d77dd799087d1c556835dca0de4321b93` | 2026-08-23T22:11:46-04:00 | none; n/a | 0/87 | SAFE branch cleanup | E1 tree fa3009a54c3544ecbf3dd316008988b537955e39 |
| `claude/goofy-perlman-490e49` | `69dc0cae7db1cd41a522dfb7d33f280038d318c2` | 2026-08-27T11:41:54-04:00 | refs/remotes/origin/main; 0/53 | 0/53 | SAFE branch cleanup | E1 tree db1666864f5e59b3a8cd9bf31ccbc759c7e97e88 |
| `claude/gracious-knuth-62ebbe` | `359a0ff5344816e898a58bb62a6aaf0572f52d77` | 2026-08-09T23:15:08-04:00 | none; n/a | 0/528 | HOLD dirty worktree | E1 tree 8dc973e71cce2d6e93a708666f532821262da919 |
| `claude/hungry-bhaskara-0e11b2` | `d3fe3acbde5a4ce4dda42206cd2a9a848e6ee15b` | 2026-08-15T20:43:27-04:00 | none; n/a | 0/364 | SAFE branch cleanup | E1 tree d721c9cc0b955d53cfbad66077635e35e5412bc1 |
| `claude/iap-enablement-writeback` | `a12ca6809add360e7e54a335b415cbd30024735a` | 2026-08-28T13:21:50-04:00 | refs/remotes/origin/claude/iap-enablement-writeback; gone | 1/50 | SAFE branch cleanup | E4 main aacc1229c1e4515917b9385edad3350d2a5dafec; patch cb702ad1db14b2bba9bd4136b2386f0edeb49e3a |
| `claude/jolly-khorana-945330` | `0a924974a990b96ec7ba98d8a1bfa45ddb430c1d` | 2026-05-22T12:54:54-04:00 | none; n/a | 1/1036 | SAFE branch cleanup | E4 main eedcd2444808213374e62c83b70d7de8eccded3f; patch a1091f12dada9add1c9766c85e072fe813c0d25a |
| `claude/jolly-leakey-d20295` | `dd893b85823614762f5d67ca269ccb4ad673f8c0` | 2026-08-16T19:30:21-04:00 | none; n/a | 0/345 | SAFE branch cleanup | E1 tree e9e962cbe161498c410ba84e97c295be1076d150 |
| `claude/jovial-meninsky-8bf0a0` | `355bddb3d044d502dbb86587188cd27859b7d342` | 2026-08-18T20:36:55-04:00 | none; n/a | 0/261 | SAFE branch cleanup | E1 tree 9eab14d276cbd0e1dd0e4382e8a608d7dd4c2d01 |
| `claude/keen-varahamihira-8986d4` | `16a9b51d4ab84b37f3f8d4e1e98e7bbc8f64a67b` | 2026-08-01T23:44:29-04:00 | none; n/a | 0/759 | SAFE branch cleanup | E1 tree 73598ce57a72730e0492e0832d02fdedd4c7645e |
| `claude/league-mate-invite-sharing-26a697` | `e92f95c16034101f1d1f925b6e90b27273d62d4a` | 2026-08-30T12:09:11-04:00 | none; n/a | 0/24 | SAFE branch cleanup | E1 tree f3f7a76ecf7a00bb007ba94bb67405bed373ec44 |
| `claude/ledger-correction-partner-summary` | `ba8e84d17ffeb63b6ec0d3e7f2f707bc9ba912b8` | 2026-08-27T11:42:34-04:00 | refs/remotes/origin/claude/ledger-correction-partner-summary; 0/0 | 1/53 | HOLD open PR #223 | E5 1 unmatched commits; 1/1 branch-touched paths differ |
| `claude/loving-shtern-12e4b1` | `c7ee5b027302fac3f2a3f70253a5055017696385` | 2026-08-15T14:24:54-04:00 | refs/remotes/origin/claude/loving-shtern-12e4b1; gone | 4/377 | HOLD unresolved content | E5 2 unmatched commits; 16/18 branch-touched paths differ |
| `claude/magical-cerf-7cfaca` | `33496d8217e946c517f87a3526db0dfa9dd0a344` | 2026-06-23T00:43:04-04:00 | none; n/a | 0/999 | SAFE branch cleanup | E1 tree a61e7928079b4e19b28f1d736151558e1d5c2e5b |
| `claude/magical-hofstadter-40cf12` | `0ad2fe9bc1c9f7cd69daf58aa0fdaa5de2a70c02` | 2026-07-10T15:37:01-04:00 | none; n/a | 0/923 | SAFE branch cleanup | E1 tree 342c0543d82ce342d9d174c284f1666abdf71bd4 |
| `claude/manual-calculator-e2e-review-39a467` | `a12c8b7bef40e04608abfbf44f0fb7096cbd6b56` | 2026-08-22T12:55:13-04:00 | refs/remotes/origin/claude/manual-calculator-e2e-review-39a467; gone | 21/106 | HOLD unresolved content | E5 20 unmatched commits; 58/83 branch-touched paths differ |
| `claude/modest-albattani-138a2d` | `5dcf29f00f42ceca2351aa130074012ae7ea8e0f` | 2026-08-14T10:00:58-04:00 | none; n/a | 0/388 | SAFE branch cleanup | E1 tree f60f2f7197f78a11ffaeff0fa21dc4972ba76bec |
| `claude/modest-cerf-12ce88` | `41c50a0997b066a027d34efa5786df46e46d89bf` | 2026-08-08T21:10:00-04:00 | none; n/a | 1/619 | HOLD unresolved content | E5 1 unmatched commits; 7/7 branch-touched paths differ |
| `claude/monthly-trial-3d` | `491427a631711958692c07785fca86ddcf1105da` | 2026-08-28T18:42:14-04:00 | refs/remotes/origin/claude/monthly-trial-3d; gone | 1/47 | SAFE branch cleanup | E4 main 5a01450c9a462136fc07f9cb3e71dca34e3e2a50; patch 22882de1da69b4c3978ec35bbe1c7c1729b1ca5b |
| `claude/mystifying-williamson-4595ad` | `2f88aaba4cd565de335ee3ded2f9cc339b4cf089` | 2026-07-10T00:15:52-04:00 | none; n/a | 0/939 | SAFE branch cleanup | E1 tree 16725f746905c8a0a0a8b178ab1dec9fa3107169 |
| `claude/new-user-feedback-06dabd` | `cd1d243bfa59d4291729730166b5a16d167dfde3` | 2026-09-03T13:56:09-04:00 | refs/remotes/origin/claude/new-user-feedback-06dabd; 0/0 | 14/5 | HOLD open PR #274 | E5 11 unmatched commits; 45/45 branch-touched paths differ |
| `claude/new-user-feedback-55320e` | `f7833d566f9fddf1c320e7f217a843ce7435a1e0` | 2026-08-24T16:25:22-04:00 | refs/remotes/origin/claude/new-user-feedback-55320e; 0/0 | 28/77 | SAFE branch cleanup | E4 main fa945925d995e8895e78285661f792f0c12f044d; patch 9670267b2ad419571af92c007a7e56b6c19ae2ea |
| `claude/new-user-feedback-d4c47d` | `af8074bd5654d26fe6d9e33ae6f77dd31bf4ca26` | 2026-08-22T01:15:24-04:00 | refs/remotes/origin/claude/new-user-feedback-d4c47d; 2/0 | 4/108 | HOLD unresolved content | E5 4 unmatched commits; 13/20 branch-touched paths differ |
| `claude/nice-lovelace-83e5e8` | `49cf21e5002ac77ea5978ba17431b4671c5ebcfc` | 2026-04-19T18:04:19-04:00 | refs/remotes/origin/main; 0/1095 | 0/1095 | SAFE branch cleanup | E1 tree 3213580b201a8b25de83a09f8e25dd243b1f90d4 |
| `claude/nifty-shtern-6dbae1` | `a40eee89abe4ed0585e0bd5a58a43aa84bbd2385` | 2026-08-02T20:20:13-04:00 | none; n/a | 0/737 | SAFE branch cleanup | E1 tree e671c3dac75e999a72b9a8f9da52de8e89488401 |
| `claude/notif-crons` | `628f7b6001e78c2c1fc9f264af6e4723b87aad64` | 2026-04-29T12:33:53-04:00 | refs/remotes/origin/claude/notif-crons; gone | 0/1080 | SAFE branch cleanup | E1 tree 6f22aa6ce1037d561cdb470b95c73a8dda0fe603 |
| `claude/notif-events` | `1dd94681ebd748d99e4233486df86ed0212aee6a` | 2026-04-27T20:41:38-04:00 | refs/remotes/origin/claude/notif-events; gone | 0/1082 | SAFE branch cleanup | E1 tree 4c4ae8ecba4762a2bb5455e9b9c06c615098b082 |
| `claude/open-feedback-summary-b43796` | `c7e756662f82fe6d48a0e03e6f73240b2d34fbd5` | 2026-09-02T18:07:02-04:00 | none; n/a | 0/10 | SAFE branch cleanup | E1 tree 081ac48384349a1e591c7924a18f85fd9a7c446f |
| `claude/outstanding-work-summary-b10a36` | `e92f95c16034101f1d1f925b6e90b27273d62d4a` | 2026-08-30T12:09:11-04:00 | none; n/a | 0/24 | SAFE branch cleanup | E1 tree f3f7a76ecf7a00bb007ba94bb67405bed373ec44 |
| `claude/peaceful-keller-de2832` | `67eec45a50d19975316dfa150b8987fab004b017` | 2026-08-16T01:15:41-04:00 | refs/remotes/origin/claude/peaceful-keller-de2832; 0/0 | 3/356 | HOLD open PR #135 | E5 3 unmatched commits; 11/11 branch-touched paths differ |
| `claude/peaceful-lumiere-e2a25b` | `2529bef953c2a3f116fffe7b71fb4f4173695225` | 2026-08-15T15:08:06-04:00 | refs/remotes/origin/main; 0/372 | 0/372 | SAFE branch cleanup | E1 tree 3ba23b3d55f9ab0114bb678d9d53ab862a47f2ef |
| `claude/pensive-kilby-d53555` | `0edc7de7351a30fe0d4b8ee3068df31874bcda2d` | 2026-07-04T23:01:12-04:00 | none; n/a | 0/998 | SAFE branch cleanup | E1 tree 47f7616f0c5f1fac6ab0828533e1bfd09691fce5 |
| `claude/platform-entry-decouple-apple` | `a08019768e39539d0eccdc03125bdfcfe7d71016` | 2026-08-26T13:08:34-04:00 | refs/remotes/origin/claude/platform-entry-decouple-apple; gone | 1/64 | SAFE branch cleanup | E4 main 3edbc33d4f9338ce42b8926aaf502aef47c6ad5a; patch 73fbd3096145bebe5957775c0884705a0a862db2 |
| `claude/propose-label-writeback` | `f7885524c22e648c9941061c58ebb665dd2623fc` | 2026-08-29T20:55:39-04:00 | refs/remotes/origin/claude/propose-label-writeback; 0/0 | 1/34 | SAFE branch cleanup | E4 main 6b4fd64a5a05ffb1b2c3142fad2c60ce976b4ff5; patch 63decc850dad7a92dd6e11a81b0324c3f2ab72e5 |
| `claude/q034-sku-ruling` | `5189a14e07fef703c1eb029f5472d5a26e3e85f5` | 2026-08-28T18:15:49-04:00 | refs/remotes/origin/claude/q034-sku-ruling; gone | 1/49 | SAFE branch cleanup | E4 main 70189f1c8ce8c42ea7af5d50550975bafb48a5bd; patch d99cbcfe7afcd0d35407a531c6d76121cea09eba |
| `claude/q035-q036-operator-answers` | `832d9ca1e34f3808ecebef3c3ceb7a1910e626e4` | 2026-09-02T15:12:26-04:00 | refs/remotes/origin/claude/q035-q036-operator-answers; 0/0 | 1/17 | SAFE branch cleanup | E4 main 02d2eac2564872ce32c3ae2dd76eed5fb945e696; patch e70bd3a27fc248641c18a3ad217b2c5e5bfd9c48 |
| `claude/ram-mascot-brief-exec-6bb3b7` | `432f8075d570a0a2c975a06d61e03555c06a8c87` | 2026-08-23T20:36:43-04:00 | none; n/a | 19/107 | HOLD unresolved content | E5 19 unmatched commits; 64/146 branch-touched paths differ |
| `claude/ram-mascot-fleeced` | `a9b86950dad2975976f383cd1fa8beb242425f02` | 2026-08-23T21:50:34-04:00 | refs/remotes/origin/claude/ram-mascot-fleeced; 0/0 | 4/90 | SAFE branch cleanup | E4 main 7ac7869ea69b936e246c7e1f82edf4df023bc6bb; patch 6724d2404f2ed1bbe444a78c3f8c0dcd7969c31e |
| `claude/reverent-gagarin-ff2b57` | `5e758d66433a6ca5613b235eba6cc3c1e678627c` | 2026-04-27T03:11:45-04:00 | refs/remotes/origin/claude/reverent-gagarin-ff2b57; gone | 0/1083 | SAFE branch cleanup | E1 tree 74cbdfcb12a7da8a4f10df1ef76273b1dfca0562 |
| `claude/sad-benz-9922d6` | `b7015531815d4513b78e0e0ba714e2bafa669553` | 2026-08-11T07:02:51-04:00 | none; n/a | 1/499 | HOLD unresolved content | E5 1 unmatched commits; 1/1 branch-touched paths differ |
| `claude/sad-brown-d5ef76` | `49cf21e5002ac77ea5978ba17431b4671c5ebcfc` | 2026-04-19T18:04:19-04:00 | refs/remotes/origin/main; 0/1095 | 0/1095 | SAFE branch cleanup | E1 tree 3213580b201a8b25de83a09f8e25dd243b1f90d4 |
| `claude/sentry-wizard` | `31f757297d5d40ac5a2bcdf1171e7468391e9a77` | 2026-04-29T17:57:29-04:00 | refs/remotes/origin/claude/sentry-wizard; gone | 1/1075 | SAFE branch cleanup | E4 main f379c8127ad668ac5b6cb1366c877b4c1c7b41ef; patch 15f09c0b449630b217ef96bf80ec980f35d4af2c |
| `claude/sharp-hamilton-2ec655` | `49cf21e5002ac77ea5978ba17431b4671c5ebcfc` | 2026-04-19T18:04:19-04:00 | refs/remotes/origin/main; 0/1095 | 0/1095 | SAFE branch cleanup | E1 tree 3213580b201a8b25de83a09f8e25dd243b1f90d4 |
| `claude/shoprite-grocery-cart-de3c37` | `e89eebb0fbedba03584b4cc99d0399f38ccf96e6` | 2026-08-29T23:14:41-04:00 | none; n/a | 0/29 | SAFE branch cleanup | E1 tree 1879146521e9ec5afb2350ab6619b8834538e903 |
| `claude/strange-jang-5fb4b7` | `f93c76af239ea37b36e63f7d3ed4190a38b04eaf` | 2026-04-29T13:19:31-04:00 | refs/remotes/origin/main; 0/1079 | 0/1079 | SAFE branch cleanup | E1 tree 21eb490403ad078c7f9c4656bb4fe1f81ac067b4 |
| `claude/suspicious-chaplygin-7dab59` | `cce8f0862ce813171e3612764c40468aa74f2e0c` | 2026-08-09T23:50:11-04:00 | none; n/a | 0/525 | HOLD dirty worktree | E1 tree 6132f28d1467bc65d742aca4501a1fa32abbccb4 |
| `claude/team-outlook-experience-27a7a1` | `3e7e25cff497f006826664de4f2d187a59771748` | 2026-08-20T17:17:41-04:00 | refs/remotes/origin/claude/team-outlook-experience-27a7a1; 2/0 | 0/151 | SAFE branch cleanup | E1 tree d434a673bbfdd3f949c06d76d2c3f7c90863126c |
| `claude/team-review-analysis-plan-1f91e3` | `5aff1ce9ab6990900fdcb20ca2e80d6532e4a044` | 2026-08-22T10:45:44-04:00 | refs/remotes/origin/claude/team-review-analysis-plan-1f91e3; 48/0 | 2/107 | HOLD dirty worktree | E5 1 unmatched commits; 1/1 branch-touched paths differ |
| `claude/tip-jar` | `bf92d4eea6e211305589636ee2a61a218fca4f42` | 2026-08-28T19:06:49-04:00 | refs/remotes/origin/claude/tip-jar; gone | 1/45 | SAFE branch cleanup | E4 main b0782d803445235d6ec0aec52bf513285a2ea469; patch c43f4ad158f234a3a94f8b806b358f921c46a572 |
| `claude/trade-decisions-review-6786b1` | `9e1a8be1a6612ef2e6b6be99ef96bf46b2d33f27` | 2026-08-21T22:10:21-04:00 | none; n/a | 0/108 | SAFE branch cleanup | E1 tree 9e498480763593fb8b3bd468ec30bbb9e705e9a0 |
| `claude/trade-disposition-review-89a94b` | `af91d6f8225d662110e67188adee1705ce219d64` | 2026-08-29T12:41:55-04:00 | none; n/a | 0/38 | SAFE branch cleanup | E1 tree c0e372099deb61582926514c624ebb2697cca560 |
| `claude/trade-model-restrictiveness-7f3975` | `32d95767dd6a16acccae07669a50f7884371d4cb` | 2026-08-23T11:45:33-04:00 | refs/remotes/origin/claude/trade-model-restrictiveness-7f3975; gone | 1/97 | SAFE branch cleanup | E4 main 23b8c8061852fb9cd52c5f146eac8dd4ba2222c7; patch ced87584a770d870d2898904f9a03245caa5accf |
| `claude/trade-model-review-101bf7` | `c211d05ccd66117c8e37b44fad57fa12934bdbd9` | 2026-08-27T23:38:07-04:00 | refs/remotes/origin/claude/trade-model-review-101bf7; 0/0 | 2/53 | HOLD open PR #224 | E5 2 unmatched commits; 13/13 branch-touched paths differ |
| `claude/trade-suggestions-review-69c9eb` | `6ac1e8a36c7a058e156b4a632e2e05fcb704fd5b` | 2026-08-20T17:31:23-04:00 | refs/remotes/origin/claude/trade-suggestions-review-69c9eb; gone | 10/152 | SAFE branch cleanup | E4 main c6e6c3c052d01e732cfc186956939df358cafb08; patch 378479178796802b264c40ad23691cddf25da705 |
| `claude/trade-verdict-elo-discrepancy-6e5606` | `867c3baaee6c5a6a4de417d2892f8c4a35a4d9ee` | 2026-08-25T05:08:19-04:00 | none; n/a | 0/66 | SAFE branch cleanup | E1 tree aa4596dae9cdd8d874e7828a418aeb7fdc9b4e3c |
| `claude/trading-engine-eval-8ab7bc` | `451d2ebd714033a3b1f6bba3fc1b939f9d086efb` | 2026-08-20T21:33:20-04:00 | none; n/a | 0/126 | SAFE branch cleanup | E1 tree 697c439818ceb3faf6cfb55b727904a5d690409e |
| `claude/trial-lengths-v2` | `0bad37ca8b5672629339a15e0d70caf8a7bb9160` | 2026-08-29T20:16:36-04:00 | refs/remotes/origin/claude/trial-lengths-v2; gone | 1/38 | SAFE branch cleanup | E4 main 209b10bae1ea81af982db4726f0a418246fc641f; patch faf06a2b03073b71161e015fd5ce50e4da191f93 |
| `claude/tweet-product-gap-review-266ff1` | `ff340b7aa188ca3a11756adbe92f64d6eb1a74f4` | 2026-08-21T01:12:23-04:00 | refs/remotes/origin/claude/tweet-product-gap-review-266ff1; 0/0 | 1/126 | HOLD open PR #160 | E5 1 unmatched commits; 1/1 branch-touched paths differ |
| `claude/vibrant-allen-023c8f` | `30070f3692cc08cd5dde8c96da2877642f4f73ca` | 2026-08-26T17:43:45-04:00 | none; n/a | 0/55 | SAFE branch cleanup | E1 tree 6b44245d0efb4286228525cd3406bc8b128987f7 |
| `claude/vigilant-spence-8583f5` | `71f63da347d72d3cec95192a6a4dbf66166ac2c9` | 2026-08-21T16:22:35-04:00 | refs/remotes/origin/claude/vigilant-spence-8583f5; gone | 20/115 | SAFE branch cleanup | E4 main 7b7c3146dec419d6e212cff3464070eb27de28a1; patch 1f9a42325c65f46ec6cfd2e3f533266f4b207d50 |
| `claude/vigilant-wozniak-382289` | `33496d8217e946c517f87a3526db0dfa9dd0a344` | 2026-06-23T00:43:04-04:00 | none; n/a | 0/999 | SAFE branch cleanup | E1 tree a61e7928079b4e19b28f1d736151558e1d5c2e5b |
| `claude/vigorous-chaum-272d92` | `ab9368f81aa580a007cc49c91240754206d3e1ec` | 2026-08-10T22:33:05-04:00 | none; n/a | 0/499 | HOLD dirty worktree | E1 tree 38f5709dd126a783f2e48010099061a1c942ed4e |
| `claude/wait-instructions-ef2095` | `867c3baaee6c5a6a4de417d2892f8c4a35a4d9ee` | 2026-08-25T05:08:19-04:00 | none; n/a | 0/66 | SAFE branch cleanup | E1 tree aa4596dae9cdd8d874e7828a418aeb7fdc9b4e3c |
| `claude/website-updates-continue-c7942b` | `c9345ae5a31c99f96792f2477615d74fc733979d` | 2026-09-02T16:09:56-04:00 | refs/remotes/origin/claude/website-updates-continue-c7942b; 2/0 | 21/13 | HOLD ignored local files | E2 base e16bb48755bd0a8ddaadc7de817da32dbd0bb987 |
| `claude/zealous-rubin` | `a93e5d861d94d220c423457afb4a88f8efb5eeb9` | 2026-04-19T13:47:49-04:00 | none; n/a | 0/1100 | SAFE branch cleanup | E1 tree 5691b5bf035b133de63673a9b79b5da380ad6e89 |
| `codex/security-data-hardening-20260904` | `606e512cd87f692eced3b92ccadb4f0192ea3449` | 2026-09-03T14:18:19-04:00 | refs/remotes/origin/main; 0/0 | 0/0 | ACTIVE new security worktree | E1 tree ad663e32c2049ad5a46bdfaac38aa245d98b1aa6 |
| `design/device-side-platform-auth` | `10f6592613c6157bf564bdbb3dc83d3242c84cb9` | 2026-08-12T13:26:25-04:00 | refs/remotes/origin/main; 1/453 | 1/453 | HOLD unresolved content | E5 1 unmatched commits; 3/3 branch-touched paths differ |
| `docs/armb-audit-consolidated` | `950fc9795951114aae6fb51e67e6dd78d522a24f` | 2026-08-19T15:30:36-04:00 | refs/remotes/origin/main; 0/191 | 0/191 | SAFE branch cleanup | E1 tree 534f58288a76e15bd09a375f473dcf2b5d834443 |
| `docs/auditor-handoff` | `613a34c3f55d4bd060c5b5ddf6a59a6f74e52bba` | 2026-08-22T11:41:21-04:00 | refs/remotes/origin/main; 0/106 | 0/106 | SAFE branch cleanup | E1 tree b866d97f1b9a4e893a52cd555fe52e5511240dde |
| `docs/espn-api-reference` | `ffec7f209687775f8ca2f13d4cd0e86866f0dc3a` | 2026-08-11T22:49:22-04:00 | none; n/a | 1/465 | HOLD unresolved content | E5 1 unmatched commits; 2/2 branch-touched paths differ |
| `docs/feedback-batch-2-prds` | `b59951c984db0318946e11c798b67788ff929f0a` | 2026-06-08T16:06:46-04:00 | refs/remotes/origin/docs/feedback-batch-2-prds; 0/0 | 1/1020 | SAFE branch cleanup | E3 8 changed paths equal current main |
| `docs/landability-c1-measurement` | `fd952b5fdf38eff16eccff7543942372f0c61777` | 2026-08-19T18:47:50-04:00 | refs/remotes/origin/docs/landability-challenger; 1/0 | 2/206 | HOLD unresolved content | E5 2 unmatched commits; 6/6 branch-touched paths differ |
| `docs/null-dwell-writeback` | `80bb318c0b6e31db48f155edd1eaca4cbb8e3412` | 2026-08-29T22:24:33-04:00 | refs/remotes/origin/docs/null-dwell-writeback; 0/0 | 1/32 | SAFE branch cleanup | E4 main d5c926fd7d2a3efc2af918560c612bd3967a2102; patch 7329294a93ebeabc6b318a3dae75c0330263113e |
| `docs/qa-reports-feedback-wave-0824` | `cf5ef852c6771a7a04242abe4c1aa970ba1256b4` | 2026-08-24T16:46:00-04:00 | refs/remotes/origin/docs/qa-reports-feedback-wave-0824; gone | 1/76 | SAFE branch cleanup | E4 main c37910518beef212847d5140f87cc3ae290fdf71; patch 5ce04622d51a62c039e93a3cc22aba2044d1ab93 |
| `docs/session-memory-writeback` | `4c0213b2a52f20e9aea7817aacffb703da39a9e7` | 2026-08-12T13:10:20-04:00 | refs/remotes/origin/main; 0/453 | 0/453 | SAFE branch cleanup | E1 tree 8a41119d6a84f9825795b9a8ebcd99865c329b0a |
| `feat/bakeoff-arm-a-challenger` | `38806e0328792f9fae70345244112ea8b661bb34` | 2026-08-19T18:01:23-04:00 | none; n/a | 0/205 | SAFE branch cleanup | E1 tree b4d7bc2511a16b40271f1c2cb06ceed9537c1ee6 |
| `feat/bakeoff-composition` | `1d49d5fc8a8fcad4291becf9eb412e48533978e3` | 2026-08-18T23:19:14-04:00 | refs/remotes/origin/main; 3/250 | 3/250 | SAFE branch cleanup | E4 main a7f8783ee1ae84a942b21025a3065704ef616cf6; patch 67780b0d505e353c62fe6a29c8d49fe1f0afb065 |
| `feat/calc-finder-merge` | `7399e182ca7607f35403a0215846d40dca7a1d38` | 2026-08-22T03:13:27-04:00 | refs/remotes/origin/main; 8/107 | 8/107 | HOLD unresolved content | E5 8 unmatched commits; 33/44 branch-touched paths differ |
| `feat/celeb-once-and-copy-tiers` | `6d60d955cf432bf09c98798a6a8f7329b398b0da` | 2026-04-30T02:33:44-04:00 | refs/remotes/origin/feat/celeb-once-and-copy-tiers; gone | 1/1063 | SAFE branch cleanup | E4 main 7325c26eba2a4f661e59ae5dfdf4ec8f6d95eb08; patch 89202ababd5a341e34b22dfa66c004cf31e51e56 |
| `feat/datetime-utcnow-cleanup` | `4a8722959d4c20ab7a324292eff4e3042de0727b` | 2026-06-08T11:48:01-04:00 | refs/remotes/origin/feat/datetime-utcnow-cleanup; 0/0 | 1/1021 | SAFE branch cleanup | E4 main 86448a6f5ffcc67d01086ee798326114881294e3; patch 72aa8b5aeb08d14fdb98037f47ea74caa3cc5b0d |
| `feat/decline-reason-player-pref` | `bcee58a2c699bd004a28f226abe2e44ae2aea66a` | 2026-08-19T00:25:28-04:00 | refs/remotes/origin/main; 0/245 | 0/245 | SAFE branch cleanup | E1 tree d0d0741949921c6bb8deb0ae469a599e8fec4bee |
| `feat/espn-credential-verify` | `2fa1ff24f0ceb143d7b23b79ed5ea874a218a619` | 2026-08-12T00:25:58-04:00 | none; n/a | 0/462 | SAFE branch cleanup | E1 tree 9b7aff83ba0ae5ea5dab828913d080ab42d33374 |
| `feat/exact-slot-pick-pricing` | `82f05c4629bbf1b0cf994c1ca69ce47f648a28d1` | 2026-08-19T22:14:34-04:00 | none; n/a | 2/158 | HOLD unresolved content | E5 2 unmatched commits; 20/20 branch-touched paths differ |
| `feat/exclude-recently-traded` | `22cd5853b3edef2fcd7bc394268b1fa726d55e52` | 2026-08-19T00:42:23-04:00 | refs/remotes/origin/main; 1/246 | 1/246 | HOLD unresolved content | E5 1 unmatched commits; 15/15 branch-touched paths differ |
| `feat/fb-07-trios-cleanup` | `fa9979bda197ca601b919f938fec55d2fd9a6314` | 2026-06-08T16:13:20-04:00 | refs/remotes/origin/feat/fb-07-trios-cleanup; 0/0 | 1/1019 | SAFE branch cleanup | E4 main bb3636ea69c88b515b942f22b4065cc6cc1e220d; patch 62aff5922b0f9142451dee66253bc9a8c71c533d |
| `feat/fb395-lineup-impact-backend` | `3e75494e47788c55100517de0238c08047c17f4e` | 2026-08-24T02:38:34-04:00 | none; n/a | 6/81 | HOLD unresolved content | E5 6 unmatched commits; 13/39 branch-touched paths differ |
| `feat/fb4-tiers-polish` | `b49e5b9eae329150783f248f824849019fc13571` | 2026-06-19T13:59:02-04:00 | refs/remotes/origin/trade-engine-v2; 1/95 | 1/988 | HOLD unresolved content | E5 1 unmatched commits; 4/4 branch-touched paths differ |
| `feat/fb4-trades-gate` | `ba1c730ef1c25f64e6393cc93b0c55fa3170fc7d` | 2026-06-19T13:55:28-04:00 | refs/remotes/origin/trade-engine-v2; 1/95 | 1/988 | HOLD unresolved content | E5 1 unmatched commits; 2/2 branch-touched paths differ |
| `feat/fb417-pushed-deck-research` | `6cd5c4902ffa49e85f748969d58a5b48f82aafcc` | 2026-09-03T01:40:30-04:00 | none; n/a | 4/10 | KEEP branch; missing registration pruned | E5 4 unmatched commits; 21/21 branch-touched paths differ |
| `feat/fb418-backend-like-exclusion` | `77a4e33b1c08acda487892d77a9e204290ccd3ec` | 2026-09-03T12:42:11-04:00 | none; n/a | 13/5 | KEEP branch; missing registration pruned | E5 10 unmatched commits; 40/40 branch-touched paths differ |
| `feat/feedback-admin-list` | `8eabe6c3d111b83fe97fdbe9a20e4bb42356fa4e` | 2026-05-21T09:03:00-04:00 | refs/remotes/origin/feat/feedback-admin-list; 0/0 | 1/1049 | SAFE branch cleanup | E4 main 8bdba1245d85b961e228b5a2542cc6914ff9d134; patch 77c66dbd12cb10c0a50da6f967926771261531c8 |
| `feat/feedback-backend-route` | `66cd2eac050c02fd005a9b13e7d1b9cf072b6cea` | 2026-05-20T19:16:12-04:00 | refs/remotes/origin/main; 0/1053 | 0/1053 | SAFE branch cleanup | E1 tree 547ed15e6843b09c31cc393921fd9a1d8d81efa7 |
| `feat/feedback-batch-4-polish` | `1d3ffca88de44f41a62e45bf3d3d43437d018785` | 2026-06-19T14:01:41-04:00 | refs/remotes/origin/feat/feedback-batch-4-polish; 0/0 | 5/988 | SAFE branch cleanup | E4 main 7a05f4e6294bc347e9d12c03b06774450249c596; patch d05d4a6998525aa62de506391b2597f724c82142 |
| `feat/feedback-mobile-sync` | `66cd2eac050c02fd005a9b13e7d1b9cf072b6cea` | 2026-05-20T19:16:12-04:00 | refs/remotes/origin/main; 0/1053 | 0/1053 | SAFE branch cleanup | E1 tree 547ed15e6843b09c31cc393921fd9a1d8d81efa7 |
| `feat/finder-config-and-draft-order` | `e174b2965864fbd0ce284a18203e2b96bd553eec` | 2026-08-08T15:21:35-04:00 | refs/remotes/origin/main; 2/629 | 2/629 | HOLD dirty worktree | E5 2 unmatched commits; 11/11 branch-touched paths differ |
| `feat/fleeced-identity` | `23b19cb527c5693be797f87f6bfb0e2d1044299d` | 2026-08-16T19:05:27-04:00 | refs/remotes/origin/main; 0/348 | 0/348 | SAFE branch cleanup | E1 tree 8e09b834b3765687aa0b677a8a3a0827ff565f94 |
| `feat/gap-sweetener-arm-c` | `9e4469fe5425138befb4cbdeddba14a45acb8b90` | 2026-08-21T13:38:58-04:00 | none; n/a | 8/124 | HOLD unresolved content | E5 8 unmatched commits; 17/31 branch-touched paths differ |
| `feat/guided-onboarding-platform-aware` | `f4b3bfb5eb45b95ffc19da8724f1ea3fd80c43d8` | 2026-08-26T17:03:48-04:00 | refs/remotes/origin/feat/guided-onboarding-platform-aware; gone | 1/58 | SAFE branch cleanup | E4 main dd2051bc21e876db370ba3b3785de9fd33c84052; patch 6a17bc899fb3de284d15ca5bc2c62f9b81ba3ef9 |
| `feat/init10-player-view-param` | `2cb2ce792269736d2f41817c54eac77031170334` | 2026-06-08T11:32:59-04:00 | refs/remotes/origin/feat/init10-player-view-param; 0/0 | 1/1022 | SAFE branch cleanup | E4 main 2dcac6e3fe317b385b4e518fc71393d4512c6637; patch 4674aaa771ca783698aff8323ee5c48a15cc676b |
| `feat/jon-357-360-362` | `43c0b4b5416502ae826ad0fdd854967a4ebb8d4e` | 2026-08-19T18:53:36-04:00 | refs/remotes/origin/main; 4/206 | 4/206 | HOLD unresolved content | E5 4 unmatched commits; 31/33 branch-touched paths differ |
| `feat/jon-360-362` | `482b07dd9b86438c20e4593570fd8eeb87d07273` | 2026-08-26T13:36:18-04:00 | refs/remotes/origin/feat/jon-360-362; 0/0 | 15/63 | SAFE branch cleanup | E4 main 9d983be480f5646b8b9f584220579ecff77c05cd; patch 74f6a6d48376d2db3eab7e1d4b4bae77c273311e |
| `feat/league-pick-value-alignment` | `b1a5024a6ef238d2b9fb30606c25548e2f386bae` | 2026-08-21T17:12:32-04:00 | refs/remotes/origin/feat/league-pick-value-alignment; gone | 2/112 | SAFE branch cleanup | E4 main 70ae4f4319ea68b0dc22195220928348afaeb481; patch 192e6a00bb94de23283bfc0bc04d1fa6cca80440 |
| `feat/light-tier-flags` | `a362a15ad810b579d73940ffa0a485d1ec55ce86` | 2026-08-20T20:48:18-04:00 | refs/remotes/origin/feat/light-tier-flags; 0/0 | 0/134 | SAFE branch cleanup | E1 tree ec73c5faefcbc62421b44970399a48e3f9742644 |
| `feat/manual-ranking-up-down-arrows` | `01d38b7aa6df2d4dd48efae55f33c279c0098b9f` | 2026-04-29T15:24:14-04:00 | none; n/a | 1/1079 | HOLD unresolved content | E5 1 unmatched commits; 3/3 branch-touched paths differ |
| `feat/mfl-send-integrated` | `3af201ac7ddd3f18c58fe0f6d7c7fd39c9ccfd4e` | 2026-08-11T16:55:59-04:00 | refs/remotes/origin/feat/mfl-send-integrated; 0/0 | 0/469 | SAFE branch cleanup | E1 tree 307a9cf736726aaf30bd4b3fa4a15d4f28b0d87b |
| `feat/mfl-trade-lifecycle` | `0e0095f22ac1516543c643194b11e5a9d3baa0ca` | 2026-08-11T14:37:28-04:00 | none; n/a | 0/494 | SAFE branch cleanup | E1 tree 046e5128326547795f57928836efcf48d7fc88ba |
| `feat/mobile-b1-manual-rankings-and-copy-tiers` | `5d5b4966090839a47bea07fb279590f09cb2aa28` | 2026-05-20T13:05:16-04:00 | none; n/a | 1/1056 | HOLD unresolved content | E5 1 unmatched commits; 7/7 branch-touched paths differ |
| `feat/mobile-b2-trends-screen` | `ab97ecb75df1779d49ea4da7f08a016df13735ae` | 2026-05-20T13:06:59-04:00 | none; n/a | 1/1056 | HOLD unresolved content | E5 1 unmatched commits; 5/5 branch-touched paths differ |
| `feat/mobile-b3-portfolio-and-multi-league` | `91b2924077c7ef3bc528076d8540211258a23595` | 2026-05-20T13:09:38-04:00 | refs/remotes/origin/feat/mobile-b3-portfolio-and-multi-league; gone | 1/1056 | HOLD unresolved content | E5 1 unmatched commits; 7/7 branch-touched paths differ |
| `feat/mobile-b4-trade-card-improvements` | `cd70e6a9e52b542d341c08be2d602fa99412273e` | 2026-05-20T13:04:47-04:00 | refs/remotes/origin/main; 1/1056 | 1/1056 | HOLD unresolved content | E5 1 unmatched commits; 5/5 branch-touched paths differ |
| `feat/mobile-b5-trade-queue` | `dc781ff5495f35f06ce5f5214f25f941fb188c50` | 2026-05-20T13:05:32-04:00 | none; n/a | 1/1056 | SUPERSEDED; removed, see queue proof | E5 1 unmatched commits; 3/4 branch-touched paths differ |
| `feat/mobile-b6-rookie-draft-board` | `f48108e79b157bc2aa6d85048bd47e3bbda1432d` | 2026-05-20T13:03:40-04:00 | refs/remotes/origin/main; 1/1056 | 1/1056 | HOLD unresolved content | E5 1 unmatched commits; 3/3 branch-touched paths differ |
| `feat/mobile-b7-league-surfaces` | `0eca32d978420915ef2b63d28f1654860d55a12b` | 2026-05-20T13:08:01-04:00 | refs/remotes/origin/feat/mobile-b7-league-surfaces; gone | 1/1056 | HOLD unresolved content | E5 1 unmatched commits; 7/7 branch-touched paths differ |
| `feat/mobile-b8-growth-loop` | `6c45fdb17c4e64ee02318b8cfdfe07154706c627` | 2026-05-20T13:09:20-04:00 | refs/remotes/origin/feat/mobile-b8-growth-loop; gone | 1/1056 | HOLD unresolved content | E5 1 unmatched commits; 8/8 branch-touched paths differ |
| `feat/notifications-clear-button` | `087e877f6aaa2688ac2b41a96d970ee5b2ec27b1` | 2026-04-27T20:38:31-04:00 | none; n/a | 1/1083 | SAFE branch cleanup | E4 main d76170663ff3d9a2a5d14ab99e9e58f49a8e6dca; patch abe280a9d6d011b5c6e3d54fa1d6861dbde45356 |
| `feat/notifications-clear-button-v2` | `3db8d31cc270c2ec782eef04dd3ac0c6e8973118` | 2026-04-29T15:26:49-04:00 | none; n/a | 1/1079 | HOLD unresolved content | E5 1 unmatched commits; 3/3 branch-touched paths differ |
| `feat/pick-slot-labels` | `2105d53ba54ff16518631065c704dd868b3e6fc0` | 2026-08-19T13:38:09-04:00 | refs/remotes/origin/main; 0/210 | 0/210 | SAFE branch cleanup | E1 tree 5c8482bd16c89b32240fa4a9084ba2c5b6931394 |
| `feat/pick-year-decay` | `8b7689a0f3a060f9b826079e65e4bc0b1f7e19d4` | 2026-08-19T00:39:08-04:00 | none; n/a | 0/245 | SAFE branch cleanup | E1 tree ce756d3692f885439eaf53f65c6ad8086001f367 |
| `feat/picker-select-all` | `a2214e9703cdb3ef878a5c5c0e30273a47582ce8` | 2026-04-29T15:26:51-04:00 | none; n/a | 1/1079 | HOLD unresolved content | E5 1 unmatched commits; 3/3 branch-touched paths differ |
| `feat/pin-tier-clamp` | `8b7689a0f3a060f9b826079e65e4bc0b1f7e19d4` | 2026-08-19T00:39:08-04:00 | none; n/a | 0/245 | SAFE branch cleanup | E1 tree ce756d3692f885439eaf53f65c6ad8086001f367 |
| `feat/placement-tier-clamp` | `7f16217bf223b4307ecced5e074334d915478f2f` | 2026-08-19T09:16:23-04:00 | none; n/a | 0/228 | SAFE branch cleanup | E1 tree 31fb10f1c70faec50a40d32faea1ff0a6ceb4760 |
| `feat/platform-unlink` | `3293f4aa1a9f6cddacce998ea0793578e31422ae` | 2026-08-12T02:26:31-04:00 | refs/remotes/origin/main; 0/460 | 0/460 | SAFE branch cleanup | E1 tree 4cd925be5b8fe746995c388003266c3832486a32 |
| `feat/receipts` | `21ad574b9871e0837a9e9ef6fa6cbc5c92818966` | 2026-08-21T14:12:05-04:00 | refs/remotes/origin/feat/receipts; gone | 14/120 | SAFE branch cleanup | E4 main 93f1fd0ebbae28fc8fdca78f504648aa5c00ec98; patch a41eb5753fd6a74dc64e2dfc00a2b4c81ddbe525 |
| `feat/round2-pick-recalibration` | `e1532a71ac8d4e82f8c2e5d6c745153dc169376b` | 2026-08-19T01:58:20-04:00 | none; n/a | 0/235 | SAFE branch cleanup | E1 tree f8819054b3014cab76cf67c40b872e237fcb6719 |
| `feat/send-auth-lazy` | `7315d8c62ec30ad47f2a27fdc7d6cbf5ef84aa05` | 2026-08-12T00:06:49-04:00 | none; n/a | 0/463 | SAFE branch cleanup | E1 tree 371965165755be35a66e3aeb86b1677c1958707f |
| `feat/send-in-espn` | `f89d8805c4ebd436705f5d59da1edc4fa9c2c82f` | 2026-08-11T18:05:57-04:00 | refs/remotes/origin/feat/send-in-espn; 0/0 | 0/465 | SAFE branch cleanup | E1 tree 0a8d54cb088b8c5cd675e40605137b27f3001e41 |
| `feat/send-in-mfl` | `5cde107fd79b4753e02c3f14d80b6ab0d322b856` | 2026-08-11T09:09:18-04:00 | refs/remotes/origin/main; 0/496 | 0/496 | SAFE branch cleanup | E1 tree e5f320a5bcac3724332b2a9240e98629f0feb3e0 |
| `feat/send-in-mfl-followups` | `45fb2cada5645f430d3b5241d77a11e78a6bb531` | 2026-08-11T14:16:27-04:00 | none; n/a | 0/495 | SAFE branch cleanup | E1 tree 6a558290b1b217f7cb6c93df108ea756f734e6e7 |
| `feat/sleeper-reachability-probe` | `3b64a4406d7fb9877169f9ae5ed87bbc7f4d1d3c` | 2026-08-13T00:13:59-04:00 | refs/remotes/origin/feat/sleeper-reachability-probe; 31/0 | 0/421 | SAFE branch cleanup | E1 tree dc6b2d7620cd9507a2d84502fdd24e25f7ad5726 |
| `feat/slot-pricing-unconditional` | `95709751e22c7ac3f08bc131c4adb57361ff53a8` | 2026-08-21T14:49:46-04:00 | refs/remotes/origin/feat/slot-pricing-unconditional; gone | 8/117 | SAFE branch cleanup | E4 main 3192d1380128d71fc05ffe99e5127c25580fb1fc; patch 17c6a6438ee6c07d62a1c71a0de5a760f5473545 |
| `feat/sweep-followups-2026-08-18` | `74e880940a8ea5084378ffa153345b99ec8a0ea7` | 2026-08-18T21:40:42-04:00 | refs/remotes/origin/main; 3/257 | 3/257 | HOLD unresolved content | E5 3 unmatched commits; 9/9 branch-touched paths differ |
| `feat/team-review-batch-2` | `f56216e5931d336051648b889c23700ce74a1398` | 2026-08-20T18:39:52-04:00 | refs/remotes/origin/feat/team-review-batch-2; 0/0 | 0/138 | SAFE branch cleanup | E1 tree a6e17a6812e2e6ae070b7dbf1b4a23940c0427c2 |
| `feat/tier-config-and-bench-fixes` | `692e6fe4b863cd370929e6244b2fba52e2663254` | 2026-04-30T01:16:42-04:00 | refs/remotes/origin/feat/tier-config-and-bench-fixes; gone | 1/1066 | SAFE branch cleanup | E4 main a339a243c34bdd1bc50c394cc4a46c995c78095c; patch 53de159afc8698bc0e3674aaeb2e175329705e33 |
| `feat/tiers-multiselect` | `c92141b386a0039510fda80b37005256c9d3b428` | 2026-04-29T22:35:00-04:00 | refs/remotes/origin/feat/tiers-multiselect; gone | 1/1068 | SAFE branch cleanup | E4 main 7757f5c5c3c52dfa5ce7931f47e729c1f4eaf810; patch 4d3cccf09feb0527c6ffd78ca39625ec9e21ebce |
| `feat/trade-presentation-v2` | `e423f602d8b795c442535b87eed6fdadbe83883f` | 2026-08-19T00:44:49-04:00 | refs/remotes/origin/main; 0/244 | 0/244 | SAFE branch cleanup | E1 tree e515cf35b176e353e58d04cd0e07db64e967fdbe |
| `feat/trade-relevance-p0` | `03dbb2984e3daa89340ae92e88d388d8950f6cc9` | 2026-08-14T22:14:27-04:00 | refs/remotes/origin/feat/trade-relevance-p0; 0/0 | 9/379 | HOLD unresolved content | E5 7 unmatched commits; 41/41 branch-touched paths differ |
| `feat/wave1-perf` | `c30f4f1d59ca9256c673a7bc44de7b9d785a8328` | 2026-06-07T13:07:06-04:00 | refs/remotes/origin/feat/wave1-perf; 0/0 | 2/1030 | HOLD unresolved content | E5 1 unmatched commits; 50/55 branch-touched paths differ |
| `feat/wave1-perf-code` | `f248197bbd348fd6790506c51fc6d474c7acb1a5` | 2026-06-07T13:07:43-04:00 | refs/remotes/origin/feat/wave1-perf-code; 0/0 | 1/1030 | SAFE branch cleanup | E4 main 464a7a2758c0d11edb41b5aa3701d0e76dfe676b; patch ad2887d4f2f1a356e20ca3e64d7490594cf678f1 |
| `feat/wave2-init08-client` | `8c2b5ec37c42e4aded02dfd7bb06bd6fd7fc4575` | 2026-06-07T14:05:22-04:00 | refs/remotes/origin/feat/wave2-init08-client; 0/0 | 1/1024 | SAFE branch cleanup | E4 main 38b127f883a761e8ae349708c759d6bb4954a496; patch 7c67c2ebf2ecf719de7ee565ec3ec9b89e2e6073 |
| `feat/wave2-init09-trade-prune` | `bec210780d0049e28c9f91c6f1c3cb4e3688c927` | 2026-06-07T13:38:09-04:00 | refs/remotes/origin/feat/wave2-init09-trade-prune; 0/0 | 1/1029 | SAFE branch cleanup | E4 main 04cdc058522e3a44c2ef08692a6fa52675e0b646; patch daf9ea48d40808678982f4881ec996909734e50b |
| `feat/wave2-init11a-13` | `040188162b92af41f980d1694d47f69ca0f0ab8c` | 2026-06-07T13:41:16-04:00 | refs/remotes/origin/feat/wave2-init11a-13; 0/0 | 1/1029 | SAFE branch cleanup | E4 main debfa4f2781b50bfc0372276e007b57f747128b9; patch 9d3c95db25e0065c088b5640315f1ce31173d00e |
| `feat/wave2-init12b` | `20bebe4ceb3065752f954c24d97b259a0bffe158` | 2026-06-07T13:36:34-04:00 | refs/remotes/origin/feat/wave2-init12b; 0/0 | 1/1029 | SAFE branch cleanup | E4 main b2117edd8987d7877e08d44aba5aae6cdaff108c; patch 0ec9f63ea178cdf2051042249c0f572890aedebb |
| `feat/wave2-init14b-db-hygiene` | `cd1248c2b314c536e119c3b130e4b1157bd7f9cf` | 2026-06-07T13:41:59-04:00 | refs/remotes/origin/main; 1/1029 | 1/1029 | SAFE branch cleanup | E4 main b8583f63fbbff2649699a9b9eaad6e78e44e995d; patch e3f9d239e7490f2a8f3b8ce692fc621c2958bb04 |
| `feat/wave2-init15-docs` | `a75ba55a6cf00d6f8a9714764e980f913bceb2f5` | 2026-06-07T13:53:37-04:00 | refs/remotes/origin/main; 1/1029 | 1/1029 | SAFE branch cleanup | E4 main 7e33cba313fb1badcae53961ae0ed5b61e65b46a; patch 2327057b4762a8b8925ab65e851d9bc17f7c1d58 |
| `feat/window-composite` | `bbc2e4b166925c4417bb5ec559a9241354b1b9fb` | 2026-08-20T21:13:18-04:00 | refs/remotes/origin/feat/window-composite; 0/0 | 0/129 | SAFE branch cleanup | E1 tree c52ce7fe948401be894289311e32cf58882832cd |
| `feedback-batch-2-base` | `c21c52071a0b7e89c317d2cd6d7b7643cd77bd62` | 2026-06-08T16:07:05-04:00 | refs/remotes/origin/main; 0/1019 | 0/1019 | SAFE branch cleanup | E1 tree befee60b6c6f02eda18b4a1f677be455387e8658 |
| `feedback-fixes-2026-08-08` | `bcd64e8f15abf70a2c33d8b8589ceb61b85b5c29` | 2026-08-08T13:58:21-04:00 | refs/remotes/origin/main; 0/634 | 0/634 | SAFE branch cleanup | E1 tree 1333100ebbcf1f6b506be284f2f55eb373e2069a |
| `fix/384-tour-device-feedback` | `a8e5ef81597b1fc0dd09449a39668eeb5f6bf4d8` | 2026-08-22T13:50:49-04:00 | refs/remotes/origin/fix/384-tour-device-feedback; gone | 1/101 | SAFE branch cleanup | E4 main ff9fcbd5d3dc6d678bb189e5774320b001dfb5fb; patch 05b4eda9dc1d00d2d0373fc1c95de3bbd141d08e |
| `fix/account-menu-hover-bridge` | `dfcb0f5699a60135c93cb408a97cd3b1d41c5cc5` | 2026-04-29T15:25:18-04:00 | none; n/a | 1/1079 | HOLD unresolved content | E5 1 unmatched commits; 1/1 branch-touched paths differ |
| `fix/armc-gen-v2-forfeits` | `31793d2326c549a17975afe9c0269b386f1967a2` | 2026-08-19T09:26:40-04:00 | none; n/a | 0/228 | SAFE branch cleanup | E1 tree a2c79aa551503e77b7812ee979520b565960de58 |
| `fix/bakeoff-outlook-lane` | `6f8daf407c51680188ada8063ab04cba24eb1cb5` | 2026-08-19T09:26:30-04:00 | none; n/a | 0/228 | SAFE branch cleanup | E1 tree f16f4dd0341ea3c57705cffc10d67350613231f7 |
| `fix/balanced-claim-fairness-gate` | `d755b3b95a62db2d8c186ff2392758d298c3a60a` | 2026-08-19T18:15:00-04:00 | none; n/a | 0/205 | SAFE branch cleanup | E1 tree 2aa139f8ea163f102f046e34ec851af382ff19b8 |
| `fix/copy-tiers-include-seed-only-players` | `4df39bef29971e01bc05882b5f069eccd50f74bd` | 2026-04-30T23:34:02-04:00 | refs/remotes/origin/fix/copy-tiers-include-seed-only-players; gone | 1/1057 | SAFE branch cleanup | E4 main 87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5; patch be61649e7da479de07c18bc7374ba14074ad61c6 |
| `fix/deck-give-headliner-cap` | `a53b14259f94ef0d0eee487ff91b05879ce831e6` | 2026-08-19T01:20:27-04:00 | none; n/a | 0/244 | SAFE branch cleanup | E1 tree fe54d99f62a87971f0c296eded1aa06cf98b9ae3 |
| `fix/espn-verification-oracle` | `7dfcd168d5e7fe0609e2533d779a691c41e09a43` | 2026-08-12T22:27:03-04:00 | refs/remotes/origin/main; 0/425 | 0/425 | SAFE branch cleanup | E1 tree af9dab764ef855cc423390e1c9a0fc53cb56cc4f |
| `fix/feedback-qc-trio-throttle` | `973ad489cda2b18880fb623eab269bd7bff921e9` | 2026-05-21T09:46:24-04:00 | refs/remotes/origin/fix/feedback-qc-trio-throttle; 0/0 | 1/1048 | SAFE branch cleanup | E4 main bd5a733ea100112b89f4d6de9dd506cce8926634; patch 03fe90fbd464121bb34c7e5dd3e687ec6b8ba783 |
| `fix/feedback-rehydrate-unsynced` | `cacde8af44ab65befae2b3941ccb777d617915a3` | 2026-05-20T20:31:17-04:00 | refs/remotes/origin/fix/feedback-rehydrate-unsynced; 0/0 | 1/1050 | SAFE branch cleanup | E4 main e52a8dcd208a9f3847d0c2883865df8857e18826; patch 9463cfeb502dc1baafa3e08aa999b8d17095b989 |
| `fix/feedback-tiers-ux` | `c693581795c7b62138a348d4b60d0c4d9003b247` | 2026-05-21T09:55:39-04:00 | refs/remotes/origin/fix/feedback-tiers-ux; 0/0 | 1/1048 | SAFE branch cleanup | E4 main 807fa66bcd999c7ea2c071296626af603ce7f527; patch 70465a1d7848ff14607d65e9e7d1346cb6b6aed8 |
| `fix/feedback-trade-match-100` | `317e42969a449c3ec34920d9e8540f65eed24114` | 2026-05-21T09:43:49-04:00 | refs/remotes/origin/fix/feedback-trade-match-100; 0/0 | 1/1048 | SAFE branch cleanup | E4 main c8a1f651bb83003f1ca356d4050b6b389aaa9fac; patch a7438531b8bafc971b8df02872d92cfd9af38c9b |
| `fix/feedback-trios-polish` | `cdeb130914e8f72916216764910caaeaf77ab1ab` | 2026-05-21T09:17:23-04:00 | refs/remotes/origin/fix/feedback-trios-polish; 0/0 | 1/1048 | SAFE branch cleanup | E4 main 4356795eedc3bf69d9c4bf6b9793e7fb6421ab87; patch ae5d521330246e478920e8a32a2a91d5f6d45565 |
| `fix/finder-conditions-and-partners-copy` | `bda0d51844b289dc509f84c71c8a44a15f742fac` | 2026-08-20T20:19:52-04:00 | refs/remotes/origin/fix/finder-conditions-and-partners-copy; 0/0 | 0/136 | SAFE branch cleanup | E1 tree 40142c7dfab3412b4c9b5c00e6b57caf19dd9940 |
| `fix/guide-band-entry-animation` | `ccb08e21bfc0e9b0c845a99bcf3e36f8eb74b4d3` | 2026-08-22T17:53:12-04:00 | refs/remotes/origin/fix/guide-band-entry-animation; gone | 1/99 | SAFE branch cleanup | E4 main fe77b287a462bed5dfa7bbe4a591aeedeaf59147; patch 84b686a3e4558d7c66d9054c7fa670435327ad8e |
| `fix/launch-privacy-legal` | `c451065c583d7313bc72dd73ea9df2dfca0037af` | 2026-08-18T22:45:27-04:00 | refs/remotes/origin/main; 0/250 | 0/250 | SAFE branch cleanup | E1 tree 3338763228976ee8ed40e188c399d839d7629693 |
| `fix/league-summary-include-self-in-joined-count` | `10a2d9bed0e9fed75eccfc137caaf72974efc55f` | 2026-04-29T15:24:24-04:00 | none; n/a | 1/1079 | HOLD unresolved content | E5 1 unmatched commits; 1/1 branch-touched paths differ |
| `fix/lift-top80-cap` | `3e80e8af408a250d56668a99208840af40349a7e` | 2026-04-30T01:43:14-04:00 | refs/remotes/origin/fix/lift-top80-cap; gone | 1/1065 | SAFE branch cleanup | E4 main d158e50d844125aaae38c8ad283b6e4ac12545ce; patch 4cf6179acae178ec09c3cde7e080afc0bf8e3601 |
| `fix/likes-you-quality-gates` | `7110af216b5037e1b2105bae149a4bf8ac66e208` | 2026-08-19T17:50:40-04:00 | none; n/a | 0/205 | SAFE branch cleanup | E1 tree 04ae08b81e9044996b719c300fd28c93064b8dad |
| `fix/manual-rankings-remove-kebab-col` | `53308eece16226ffbcc7a068171945d3408e6b4b` | 2026-04-29T15:25:29-04:00 | none; n/a | 1/1079 | HOLD unresolved content | E5 1 unmatched commits; 3/3 branch-touched paths differ |
| `fix/manual-rankings-remove-kebab-column` | `087e877f6aaa2688ac2b41a96d970ee5b2ec27b1` | 2026-04-27T20:38:31-04:00 | none; n/a | 1/1083 | SAFE branch cleanup | E4 main d76170663ff3d9a2a5d14ab99e9e58f49a8e6dca; patch abe280a9d6d011b5c6e3d54fa1d6861dbde45356 |
| `fix/mobile-warm-player-cache-on-init` | `5e52cdac886deae8fa12fa4a314ddb72d28bd8de` | 2026-05-20T19:15:56-04:00 | refs/remotes/origin/fix/mobile-warm-player-cache-on-init; gone | 1/1054 | SAFE branch cleanup | E4 main 66cd2eac050c02fd005a9b13e7d1b9cf072b6cea; patch 9623f2ff5b158660b93be6804587a4d72b01014b |
| `fix/package-benchmark-sweetener` | `7fe1e9b61eb1685e2709c918c34cc79ce460f947` | 2026-08-21T12:38:14-04:00 | refs/remotes/origin/fix/package-benchmark-sweetener; gone | 10/123 | SAFE branch cleanup | E4 main d42872f214628b4bd162f115666966a4eba641d5; patch de864dbec88284096f1d37f4db5e64af741c7d6b |
| `fix/pick-assignment-missing-user-team` | `7b9df5db0327e8a86c7319282579407c2749cddf` | 2026-08-08T14:22:21-04:00 | none; n/a | 1/632 | SAFE branch cleanup | E4 main fc260dea52f39590f4e8b3ac100e83a0d4a5c424; patch f7961aba9e5d05ad1ba4007ce1fbc26ea3254ce9 |
| `fix/pick-assignment-missing-user-team-clean` | `fc260dea52f39590f4e8b3ac100e83a0d4a5c424` | 2026-08-08T14:23:14-04:00 | refs/remotes/origin/main; 0/630 | 0/630 | SAFE branch cleanup | E1 tree 5c138af3a1ce940ac7811f37958044a854908dda |
| `fix/pick-horizon` | `2009de5996ed103530245ef8f695715c838bb885` | 2026-08-19T13:38:20-04:00 | none; n/a | 0/210 | SAFE branch cleanup | E1 tree fca6273c3df4825a75176929adaf921bf80fa697 |
| `fix/pick-round3-value` | `e777e9d4f1165d5aebf4877a7b101fdc60153929` | 2026-08-19T09:27:46-04:00 | none; n/a | 0/228 | SAFE branch cleanup | E1 tree 7046ae170f673bce451ea2e116e487c82db2ba9a |
| `fix/preserve-tier-overrides` | `a726995d872952d0425f7098ae69405b47bd07f1` | 2026-04-29T23:23:25-04:00 | refs/remotes/origin/fix/preserve-tier-overrides; gone | 1/1067 | SAFE branch cleanup | E4 main ff8a116b487fb4aa351543b065d72f53affd092f; patch 09b69bd8ff3b2353f320e29794bc98a6dc783bae |
| `fix/rankings-progress-monotonic-unlock` | `2dd277e77f0b6f2d54a4be17c5a2b0d737fade18` | 2026-04-29T17:41:19-04:00 | refs/remotes/origin/fix/rankings-progress-monotonic-unlock; gone | 1/1076 | SAFE branch cleanup | E4 main 67e5a27bfd9a5a7b5aaf6001f85947a634d286b0; patch af9cdc2e0a403c3604a843b50a30ed7b3a388500 |
| `fix/remove-trios-info-icon` | `087e877f6aaa2688ac2b41a96d970ee5b2ec27b1` | 2026-04-27T20:38:31-04:00 | none; n/a | 1/1083 | SAFE branch cleanup | E4 main d76170663ff3d9a2a5d14ab99e9e58f49a8e6dca; patch abe280a9d6d011b5c6e3d54fa1d6861dbde45356 |
| `fix/review-batch-backend-perf` | `8c3a5550b63a53f27af467bbfac280266f41df76` | 2026-05-24T16:00:36-04:00 | refs/remotes/origin/fix/review-batch-backend-perf; 0/0 | 1/1035 | SAFE branch cleanup | E4 main 4f83805d7d50006b2718464ae6e9b9d857787b12; patch cbc8d205c8cf3f3267abc0caf23c1ec01ece2d01 |
| `fix/review-cache-and-mutations` | `9d99ab81efec8e35f3a1f5aa08f3a931b850f325` | 2026-05-24T16:07:22-04:00 | refs/remotes/origin/fix/review-cache-and-mutations; 0/0 | 1/1031 | SAFE branch cleanup | E4 main a1142da0c20d3492d12b6234ae2e082816de249b; patch a90152b45af6818eeb4ed11e4d7b68bee36d43fd |
| `fix/review-flags-and-notifications` | `78b1568fa9275544bb2b32220b169816d208825d` | 2026-05-24T15:58:56-04:00 | refs/remotes/origin/fix/review-flags-and-notifications; 0/0 | 1/1035 | SAFE branch cleanup | E4 main ae029bce29b9bf987db77522c72c0417e6dff4bb; patch 5608f78212a8a3c52dc18121ea25312c302c1ecc |
| `fix/session-init-parallelization` | `5e1a5a879b6cad551b4e0d38f35c51dddd47fef4` | 2026-05-24T16:04:12-04:00 | refs/remotes/origin/fix/session-init-parallelization; 0/0 | 1/1032 | SAFE branch cleanup | E4 main b9187716ab9181444cf4d38b6fa0ce2b43e8000a; patch e2ab6a882337e6eb82e50ea82c03b315948236a4 |
| `fix/test-user-logins` | `be9afbd4482fbd432bb2c283bf778d2eafa970a5` | 2026-06-23T00:42:58-04:00 | refs/remotes/origin/fix/test-user-logins; 0/0 | 1/1000 | SAFE branch cleanup | E4 main 33496d8217e946c517f87a3526db0dfa9dd0a344; patch d204d390c4d2d56856cee8f58186f71e7d037c4f |
| `fix/test-user-logins-tev2` | `34b8d4c3eeaf835efd4bcae94721cf30ae126965` | 2026-06-23T20:56:03-04:00 | refs/remotes/origin/fix/test-user-logins-tev2; 0/0 | 1/987 | SAFE branch cleanup | E4 main 33496d8217e946c517f87a3526db0dfa9dd0a344; patch d204d390c4d2d56856cee8f58186f71e7d037c4f |
| `fix/tier-arrows-edge-detection` | `1b4a9a4ce866d8cd7f5c72badd14cf8da0e2099a` | 2026-04-29T17:33:05-04:00 | refs/remotes/origin/fix/tier-arrows-edge-detection; gone | 1/1077 | SAFE branch cleanup | E4 main 6f908746c52ff10494606ea04a0cced2304ebaeb; patch 553f5061e6003272197c0dd7371b61e5d3dd7a69 |
| `fix/tier-overrides-survive-swipes` | `97a29130fa31cd5c861d5f0acc299eadc4d2fa36` | 2026-04-30T02:07:42-04:00 | refs/remotes/origin/fix/tier-overrides-survive-swipes; gone | 1/1064 | SAFE branch cleanup | E4 main 595e770b174a12cad468cad4f4d2461d2e21f055; patch c800008eba727d741dfe260a001492d3aa2344c2 |
| `fix/tiers-drag-worklet-crash` | `ee8c48b5ca0db2d80a9ae0d0f61cb34b709a03f1` | 2026-05-20T19:57:40-04:00 | refs/remotes/origin/fix/tiers-drag-worklet-crash; 0/0 | 1/1052 | SAFE branch cleanup | E4 main f5c8bc3dbe20417e188de771c7aa3329abde4b5a; patch 6c4f3c3343d363669f7ccf44a7d8988039e9a4c6 |
| `fix/tiers-drop-coord-space` | `0a924974a990b96ec7ba98d8a1bfa45ddb430c1d` | 2026-05-22T12:54:54-04:00 | refs/remotes/origin/fix/tiers-drop-coord-space; 0/0 | 1/1036 | SAFE branch cleanup | E4 main eedcd2444808213374e62c83b70d7de8eccded3f; patch a1091f12dada9add1c9766c85e072fe813c0d25a |
| `fix/tiers-format-sync` | `b68c193de946f389a778fe151b566202d788c385` | 2026-04-30T23:00:22-04:00 | refs/remotes/origin/fix/tiers-format-sync; gone | 1/1058 | SAFE branch cleanup | E4 main b29e6e37843d80b59a8259fb72854dbf1b9753b1; patch 38ba08f359675455dda442bc7c399187111a8f83 |
| `fix/tiers-manual-routing` | `c5397b4b36e240f44c6498fa39e3810b07341601` | 2026-04-29T15:24:41-04:00 | none; n/a | 1/1079 | HOLD unresolved content | E5 1 unmatched commits; 1/1 branch-touched paths differ |
| `fix/tiers-multiselect` | `ad8471b51f6d92b6c35871c42055061dbd2d32c9` | 2026-06-09T14:04:27-04:00 | refs/remotes/origin/fix/tiers-multiselect; 0/0 | 1/1011 | SAFE branch cleanup | E4 main ba647dedf3c5abaec84a45531819257ad9e03146; patch d8429c761ffcafe84064133cda686d9dda59db58 |
| `fix/trade-job-fmt-undefined` | `6a5a08d92decd7524e561bb0b6ff97c55db5ba1e` | 2026-04-29T20:06:38-04:00 | refs/remotes/origin/fix/trade-job-fmt-undefined; gone | 1/1072 | SAFE branch cleanup | E4 main e6695b5ee087fad76728ac20c716ca9737cd12a4; patch 0dc4dd61bc00688d443a5a2409d1f131c3df196c |
| `fix/trios-remove-college` | `085fb777c50e91039f51ce9999951f6a4a6eaeea` | 2026-04-29T15:23:44-04:00 | none; n/a | 1/1079 | HOLD unresolved content | E5 1 unmatched commits; 1/1 branch-touched paths differ |
| `fix/trios-remove-college-2026-04-26` | `087e877f6aaa2688ac2b41a96d970ee5b2ec27b1` | 2026-04-27T20:38:31-04:00 | none; n/a | 1/1083 | SAFE branch cleanup | E4 main d76170663ff3d9a2a5d14ab99e9e58f49a8e6dca; patch abe280a9d6d011b5c6e3d54fa1d6861dbde45356 |
| `fix/trios-remove-info-icon-2026-04-26` | `bd33082d0d125f2ff17088b3f84618e07b1b71d5` | 2026-04-29T15:24:17-04:00 | none; n/a | 1/1079 | HOLD unresolved content | E5 1 unmatched commits; 1/1 branch-touched paths differ |
| `fix/trios-subtab-active-highlight` | `472b3aa359d90394eb6f4d06a663f5ce05eda29f` | 2026-04-29T15:23:27-04:00 | none; n/a | 1/1079 | HOLD unresolved content | E5 1 unmatched commits; 1/1 branch-touched paths differ |
| `fix/web-phase0` | `40390013672cae0079276ceb79b9e85146c13626` | 2026-08-26T09:38:24-04:00 | refs/remotes/origin/main; 8/66 | 8/66 | HOLD unresolved content | E5 7 unmatched commits; 19/36 branch-touched paths differ |
| `fix/web-trades-snapshot-poller` | `e5fc5cf6887172e04d58da3c5a215d739821756d` | 2026-04-29T17:56:35-04:00 | refs/remotes/origin/fix/web-trades-snapshot-poller; gone | 1/1075 | SAFE branch cleanup | E4 main 28213dfae86324e17d953bc8c2aa9a443b47ffbf; patch e608e76d7bff0493cc1fda91aa8e09be8549c9d4 |
| `infra/render-cron-migration` | `57300ae55db004d9981e4c375972701078459091` | 2026-08-09T22:34:45-04:00 | refs/remotes/origin/infra/render-cron-migration; 0/0 | 1/531 | HOLD open PR #102 | E5 1 unmatched commits; 3/3 branch-touched paths differ |
| `ledger/2026-09-03-fb413-ship` | `1aede146919b9c896944ebd6c46398ab2e64f1d8` | 2026-09-03T00:19:51-04:00 | refs/remotes/origin/ledger/2026-09-03-fb413-ship; 0/0 | 2/9 | HOLD ignored local files | E4 main 6ccd6698e97fbac9b37d31e451cf0132060e7b6c; patch 041bce1e2f9bc2c54fb336110e96210538486943 |
| `living-memory-revival` | `f949fec2639dc509d92af217d5c84be52ea76f75` | 2026-08-08T14:17:49-04:00 | refs/remotes/origin/living-memory-revival; 0/0 | 1/632 | SAFE branch cleanup | E4 main f714f52589c32970c193c2a11454790aca3871af; patch 09b6e298f22b4f54839da6954dd15ad98c9b9e1d |
| `main` | `1d0152fc8f70868000c96e53544e680287e9ced8` | 2026-09-03T13:32:24-04:00 | refs/remotes/origin/main; 0/2 | 0/2 | Protected main | E1 tree e2718f18e8b2b3889a6fd593f2bceb14d2b68c9c |
| `mobile/independent-followups` | `087e877f6aaa2688ac2b41a96d970ee5b2ec27b1` | 2026-04-27T20:38:31-04:00 | refs/remotes/origin/mobile/independent-followups; gone | 1/1083 | SAFE branch cleanup | E4 main d76170663ff3d9a2a5d14ab99e9e58f49a8e6dca; patch abe280a9d6d011b5c6e3d54fa1d6861dbde45356 |
| `mobile/session-expired-recovery` | `2a5ca54a518b60de307988ea153851295823c4aa` | 2026-04-30T02:37:21-04:00 | refs/remotes/origin/mobile/session-expired-recovery; gone | 1/1062 | SAFE branch cleanup | E4 main 1e4afd85ac2b02f5ad47224ece7490cc5edd7a1a; patch 4a9ee930c620a05a250c5ce69779c3415bbbf781 |
| `mobile/tiers-persistence-parity` | `a834d383d68ff0a945bda7cb0803cf7e2342f904` | 2026-04-30T02:42:37-04:00 | refs/remotes/origin/mobile/tiers-persistence-parity; gone | 1/1062 | SAFE branch cleanup | E4 main 57a8fd265f87e068f58490547e365b9fc5c5b3d0; patch 7f0df885970b887b754863a1a99b407726db489f |
| `mobile/web-parity-2026-04-29` | `f5446bbade03074b88d0c5f5a3adcad78b8a3e02` | 2026-04-29T18:07:35-04:00 | refs/remotes/origin/mobile/web-parity-2026-04-29; gone | 1/1073 | SAFE branch cleanup | E4 main 4f45d261306215a5f678af627fa70b9f354205a7; patch b7f674aa6205c9ced2d8d2ad0fbfab90d744c69a |
| `mobile/yellow-followups` | `f7aa97752d5d3f96635cf39d37d70576ca236fbf` | 2026-04-27T03:13:16-04:00 | refs/remotes/origin/mobile/yellow-followups; gone | 2/1086 | HOLD unresolved content | E5 2 unmatched commits; 7/7 branch-touched paths differ |
| `p1-remediation-2026-08-11` | `5a4a63217cb824ddcb3202e1f5af75552b496cac` | 2026-08-12T23:00:47-04:00 | refs/remotes/origin/main; 7/425 | 7/425 | HOLD ignored local files | E5 7 unmatched commits; 34/34 branch-touched paths differ |
| `perf/dp-single-fetch` | `50e0451d4db14f91535479c84ae9a42113037900` | 2026-08-19T15:01:44-04:00 | refs/remotes/origin/main; 0/206 | 0/206 | SAFE branch cleanup | E1 tree 7325868a227d1b7bad9595f8fdd13651c3d765ee |
| `perf/find-a-trade-faster-pregen` | `dc83ce41ff684f396c3ad05c1791e334aa96cad2` | 2026-04-29T20:17:05-04:00 | refs/remotes/origin/perf/find-a-trade-faster-pregen; gone | 1/1071 | SAFE branch cleanup | E4 main d9d17e05cb08a76898f4f44b2d6a18a621d4409b; patch bc26213cd63668a9ca14f1fb527bcab677d54b69 |
| `perf/find-a-trade-tighter-cap` | `b5f1f39eafdfb786d1f811d42305fedabf36869e` | 2026-04-29T20:21:09-04:00 | refs/remotes/origin/perf/find-a-trade-tighter-cap; gone | 1/1070 | SAFE branch cleanup | E4 main 1091f3605f8370fdf1134c227550fc1135e2a94b; patch 5f65cad946fa6217699a9ee0b7266eb99aca3c72 |
| `perf/league-matches-progressive-paint` | `9a3475dfae187d8c7de27170a17de9c651b3e086` | 2026-05-21T09:52:16-04:00 | refs/remotes/origin/perf/league-matches-progressive-paint; 0/0 | 1/1048 | SAFE branch cleanup | E4 main 2bf4484c4a4ec29255a708b32f2d63c9ca4b3bea; patch c0569adfe3868e7f88ac58e68f937718c012556d |
| `perf/trade-tier-priority` | `b12488d25c2454b461d4b830d0ed79415d08fed0` | 2026-04-29T20:33:01-04:00 | refs/remotes/origin/perf/trade-tier-priority; 0/0 | 1/1069 | SAFE branch cleanup | E4 main 6aa1255d2f79fc003a5e5ac28bd6e7776f003712; patch e627b137e8389425ad0dc711c5da6374425377e6 |
| `perf/trios-fast-load` | `dd8f95b0d2d5d433ac42c3492c549a1a0eab3163` | 2026-05-24T16:00:09-04:00 | refs/remotes/origin/perf/trios-fast-load; 0/0 | 1/1035 | SAFE branch cleanup | E4 main 827add1570ad9434bbb9067d067e33f9bf232eca; patch fdd256de8605246659badd4a6cf8b865a4dba39c |
| `perf/warm-endpoint-and-boot-ping` | `0eca3c4e003a90578a3ed6f0e3a4bc64f478bd05` | 2026-05-21T09:53:09-04:00 | refs/remotes/origin/perf/warm-endpoint-and-boot-ping; 0/0 | 1/1048 | SAFE branch cleanup | E4 main 71ba9b1edcd577ec64b8c19ba9fd7f953df38fdf; patch 869c6f1f35559416349ad57568dd4aed3c3d92bf |
| `plan/receipts` | `557260400630dc6fac14161a7cf1d5c37967e3cf` | 2026-08-21T08:30:39-04:00 | refs/remotes/origin/main; 6/126 | 6/126 | SAFE branch cleanup | E3 7 changed paths equal current main |
| `recovery/ledger-entry-login-option` | `8dca63c33b1a1ae6a7ce3a35fd25b5335c923c9a` | 2026-08-26T15:45:26-04:00 | refs/remotes/origin/recovery/ledger-entry-login-option; gone | 1/60 | SAFE branch cleanup | E4 main 6c8d2c86bcdf406771d9d904ee8201ef956657fa; patch 076d1f3ee988faa0940388318f087d470259df3d |
| `recovery/ledger-landing-platform-options` | `81001c272140fdd41277bdbc71cfa0a886888036` | 2026-08-26T09:50:08-04:00 | refs/remotes/origin/recovery/ledger-landing-platform-options; gone | 1/65 | SAFE branch cleanup | E4 main ec031f91a4883574fea4544da451711b7ef9b93f; patch fc67fac360a6dabc9298188db93ae84807318ab6 |
| `recovery/ledger-platform-entry-decouple` | `141546aec74a4845d7567ba4149bd0445b99f091` | 2026-08-26T13:20:20-04:00 | refs/remotes/origin/recovery/ledger-platform-entry-decouple; gone | 1/63 | SAFE branch cleanup | E4 main 5a413df5a61eac0bad19daf81fa5c5537054e95f; patch c946b4a11a4e323f2e6f153a26f998cc3a17e542 |
| `recovery/ledger-v1168-sweep` | `20b1d22a7d8db1b8d9fb1c4753174a834b140a28` | 2026-08-26T17:35:12-04:00 | refs/remotes/origin/recovery/ledger-v1168-sweep; gone | 1/56 | SAFE branch cleanup | E3 1 changed paths equal current main |
| `release/v1.16.8` | `364d8d7cdd97d90793f273f6411f134d77fbf3f7` | 2026-08-26T16:50:37-04:00 | refs/remotes/origin/release/v1.16.8; gone | 1/59 | SAFE branch cleanup | E4 main 0f0a8a32670ea9736a6f7880f42eb7376f46dca1; patch 9e20fa6bf4db6b66052e97f7d5e5afb304442a45 |
| `release/v1.16.8-record` | `96e48ed7a0809c86c2653c83d74613c07d203e67` | 2026-08-26T17:24:00-04:00 | refs/remotes/origin/release/v1.16.8-record; gone | 1/57 | SAFE branch cleanup | E4 main 56ee2994c199453b6e5a46ca1a1dfefa86854bca; patch 928aa804f51846e71d2d7e172872421179e00229 |
| `rescue/session-gate-and-207-docs` | `244d151c38468760a67a594315a84425434fce0a` | 2026-08-08T15:06:10-04:00 | refs/remotes/origin/main; 2/630 | 2/630 | HOLD unresolved content | E5 2 unmatched commits; 16/16 branch-touched paths differ |
| `research/ktc-pick-comparison` | `be9237b23e0f42aaf41a8a69cd5a0441824dfc38` | 2026-08-19T01:18:04-04:00 | none; n/a | 1/245 | SAFE branch cleanup | E4 main 77cce9b6f6561682995ad5eedd52355b0d1a7745; patch 41cb226b8e4247450f4e877f3db00cd6eaf2edb9 |
| `review/fit-challenger-eng` | `a140eca8e82e461e5af8221f7ab169213efd2f6a` | 2026-08-19T22:30:47-04:00 | none; n/a | 5/158 | HOLD unresolved content | E5 5 unmatched commits; 30/31 branch-touched paths differ |
| `rookie-draft/qa-flag-flip` | `33a51831a3d52f14a6b6661ea30432417ce95508` | 2026-08-06T13:50:08-04:00 | none; n/a | 0/682 | SAFE branch cleanup | E1 tree da2f2c02d6dc13547cce1c45f47ee73022f12813 |
| `send-in-mfl` | `1ea7c793e197659ff7ec4a89a16ac592bf32cc24` | 2026-08-11T09:10:55-04:00 | refs/remotes/origin/main; 6/499 | 6/499 | HOLD unresolved content | E5 6 unmatched commits; 30/30 branch-touched paths differ |
| `session-2026-08-10` | `ab9368f81aa580a007cc49c91240754206d3e1ec` | 2026-08-10T22:33:05-04:00 | refs/remotes/origin/main; 0/499 | 0/499 | SAFE branch cleanup | E1 tree 38f5709dd126a783f2e48010099061a1c942ed4e |
| `session-2026-08-11-169` | `ffd55f84ade5f8d248cfefd9c1e306830aca186d` | 2026-08-11T10:56:25-04:00 | refs/remotes/origin/main; 0/497 | 0/497 | SAFE branch cleanup | E1 tree 75f1bd3645f821b81b91c7ade0d0c9177f4c6c44 |
| `session-2026-08-13-notif-ship` | `05e87d848aced60a094b6e0f8891b3b01d5d94a8` | 2026-08-15T19:38:36-04:00 | none; n/a | 9/421 | HOLD dirty worktree | E5 8 unmatched commits; 38/46 branch-touched paths differ |
| `ship/analysis` | `fe191f6605d23a2a5252d8c445769ba20a321864` | 2026-08-19T21:50:58-04:00 | refs/remotes/origin/main; 0/158 | 0/158 | SAFE branch cleanup | E1 tree 9658bdd220c2df333e03208f2d4aa39c4cdf0190 |
| `ship/armc-sweetener` | `45406790e073c10457978e0dc2c3e29913ecd08d` | 2026-08-21T14:30:43-04:00 | refs/remotes/origin/ship/armc-sweetener; gone | 2/118 | SAFE branch cleanup | E4 main 3df71c06bd001bff7bfcd825a6a2dc4773fa125c; patch b78248e3a23588b7559bf7fb4d026bd292f1ccb4 |
| `ship/armed` | `24be3956f98d7c4cd4c4bd9285b64f9f8a6fd7f7` | 2026-08-19T18:36:37-04:00 | refs/remotes/origin/main; 0/193 | 0/193 | SAFE branch cleanup | E1 tree e77e9879d3b3c64168bd26f533f799d4fc581694 |
| `ship/bakeoff-dark` | `579a9e3db984a77b592bf0dc6966442bc47622b7` | 2026-08-19T02:36:13-04:00 | refs/remotes/origin/main; 0/235 | 0/235 | SAFE branch cleanup | E1 tree 7a8a7d3dcfdc66a7f6cb7f2805e79c78edd66d30 |
| `ship/bakeoff-interleave-on` | `a12240657e6d7442acc309766a6e8312e7ef8af1` | 2026-08-19T02:55:53-04:00 | refs/remotes/origin/main; 0/234 | 0/234 | SAFE branch cleanup | E1 tree 2e42f2704191430f4d4d3239ea8dcf8aa08b4a2b |
| `ship/co-owner-ledger` | `1bf064572ee79db11c7ee7ad84be6e4de6efb5b2` | 2026-08-15T13:23:22-04:00 | refs/remotes/origin/main; 0/377 | 0/377 | SAFE branch cleanup | E1 tree 1289bcf2da349d1ba8f51adc018a725dab3767a7 |
| `ship/composition` | `a7f8783ee1ae84a942b21025a3065704ef616cf6` | 2026-08-18T23:20:49-04:00 | refs/remotes/origin/main; 0/249 | 0/249 | SAFE branch cleanup | E1 tree ee067957abac3c6445fe617a0bf5a3f4cc124715 |
| `ship/disable-presentation` | `a12240657e6d7442acc309766a6e8312e7ef8af1` | 2026-08-19T02:55:53-04:00 | refs/remotes/origin/main; 0/234 | 0/234 | SAFE branch cleanup | E1 tree 2e42f2704191430f4d4d3239ea8dcf8aa08b4a2b |
| `ship/engine-batch` | `a130dfc2e4b0679f3479f1ba84c5fbd77fa366dd` | 2026-08-19T03:03:36-04:00 | refs/remotes/origin/main; 0/229 | 0/229 | SAFE branch cleanup | E1 tree 93b4d4da48d407d9db0146e544281d6ade8b504f |
| `ship/four-fixes` | `28c12a0a6b71212cf7f957d716c1f9360b6a5984` | 2026-08-19T10:30:01-04:00 | refs/remotes/origin/main; 0/221 | 0/221 | SAFE branch cleanup | E1 tree bac5774dfe5b7dd28f429283cc15b2297c7e21ae |
| `ship/mobile-1150` | `19f6fe87ec5103307541f53cad43268e93dec29d` | 2026-08-19T01:50:15-04:00 | refs/remotes/origin/main; 0/236 | 0/236 | SAFE branch cleanup | E1 tree 60aca79dfe0b083a03b9fa996eb88a10f30daece |
| `ship/pick-fixes` | `16d277f5c12a8d1c36b36534b74ac1cabe0df0a3` | 2026-08-19T14:25:23-04:00 | refs/remotes/origin/main; 0/207 | 0/207 | SAFE branch cleanup | E1 tree 98f3467dbc6a96d2f77a6597a2720b81f547808b |
| `ship/pickyear` | `8b7689a0f3a060f9b826079e65e4bc0b1f7e19d4` | 2026-08-19T00:39:08-04:00 | refs/remotes/origin/main; 0/245 | 0/245 | SAFE branch cleanup | E1 tree ce756d3692f885439eaf53f65c6ad8086001f367 |
| `spike/send-in-espn-write` | `17eb62b618d3d38db00ead88b70c5b4c53bb76c1` | 2026-08-11T08:47:17-04:00 | refs/remotes/origin/main; 1/499 | 1/499 | HOLD unresolved content | E5 1 unmatched commits; 5/5 branch-touched paths differ |
| `sync-main-temp` | `66cd2eac050c02fd005a9b13e7d1b9cf072b6cea` | 2026-05-20T19:16:12-04:00 | refs/remotes/origin/main; 0/1053 | 0/1053 | SAFE branch cleanup | E1 tree 547ed15e6843b09c31cc393921fd9a1d8d81efa7 |
| `teardown-remediation` | `30492ac73d5a70dc5ebdb8614a43d55887508648` | 2026-08-06T01:16:59-04:00 | none; n/a | 4/706 | HOLD unresolved content | E5 2 unmatched commits; 25/32 branch-touched paths differ |
| `trade-engine-v2` | `ca2b26aad6c695a662895fee8c5108fd291af200` | 2026-07-19T21:26:09-04:00 | refs/remotes/origin/trade-engine-v2; 0/0 | 0/893 | SAFE branch cleanup | E1 tree ef9a1f2e42fd55de996cfec8dd437512ae877a0a |
| `verify-batch-2` | `bb3636ea69c88b515b942f22b4065cc6cc1e220d` | 2026-06-08T16:26:44-04:00 | refs/remotes/origin/main; 0/1012 | 0/1012 | SAFE branch cleanup | E1 tree 2138311a6ef9b4a74d62a24f8414cdc4e19fcd4d |
| `web/tiers-within-tier-reorder` | `6a152bf52b72d13f91e6a89ee2d69f1f92696f74` | 2026-04-29T15:40:32-04:00 | refs/remotes/origin/web/tiers-within-tier-reorder; gone | 1/1079 | SAFE branch cleanup | E4 main 39b8c3e57bf001fe1a344734d28bf9ec58d7821f; patch 5dec068762b326c4de7c3d325c05a3c29a84d57d |
| `worktree-agent-a05d00e6` | `dddb1ff826951616286af3e854043e59dff2d63e` | 2026-04-29T15:29:45-04:00 | none; n/a | 1/1079 | HOLD unresolved content | E5 1 unmatched commits; 4/4 branch-touched paths differ |
| `worktree-agent-a064c586eb5fd3310` | `1580064cb88cb2f86f0264b03f76d500e2266984` | 2026-07-20T13:30:04-04:00 | none; n/a | 0/886 | SAFE branch cleanup | E1 tree 75e40d2ea6aaf0ad556e6b00dbb3e7bed1822f12 |
| `worktree-agent-a06e7515c090bf5ca` | `791a6df3e4307530e7e823be60183a647b298425` | 2026-08-08T09:31:36-04:00 | none; n/a | 0/652 | SAFE branch cleanup | E1 tree d5b41b8227d7c4c690e86cec339de10888b8f384 |
| `worktree-agent-a073f9cfc8b08f4a0` | `ab9368f81aa580a007cc49c91240754206d3e1ec` | 2026-08-10T22:33:05-04:00 | none; n/a | 0/499 | SAFE branch cleanup | E1 tree 38f5709dd126a783f2e48010099061a1c942ed4e |
| `worktree-agent-a09286dd2a0cefc88` | `26f76f3baf7827ea49dfb001a4418f1ca669508f` | 2026-07-25T19:16:04-04:00 | none; n/a | 0/855 | SAFE branch cleanup | E1 tree ab8da31fae6f5053d77e5d4cbe75db1bbec2d2f8 |
| `worktree-agent-a099babc74eec6d1a` | `87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5` | 2026-04-30T23:34:23-04:00 | none; n/a | 0/1056 | SAFE branch cleanup | E1 tree e5533e4907df0480314ff1f963619d9f481c7c8e |
| `worktree-agent-a0bc3ef65ca534b5c` | `f65bab75adf3a949c82402a4f0c6767166bcb142` | 2026-08-11T11:19:09-04:00 | none; n/a | 0/478 | SAFE branch cleanup | E1 tree 789ea1f8df9ead38ea4dd664dd0c6cdca4324db6 |
| `worktree-agent-a0bdfe68ec9ca11b4` | `35b63fc1dba4948ee7afb908cfaf401bbdc92e56` | 2026-08-02T00:03:36-04:00 | none; n/a | 0/758 | SAFE branch cleanup | E1 tree 5a41487cd4ed9a92a9ab18a5be319070b8b70e93 |
| `worktree-agent-a0c99997` | `f93c76af239ea37b36e63f7d3ed4190a38b04eaf` | 2026-04-29T13:19:31-04:00 | none; n/a | 0/1079 | SAFE branch cleanup | E1 tree 21eb490403ad078c7f9c4656bb4fe1f81ac067b4 |
| `worktree-agent-a0d2eb20f30acda42` | `7d259d43936cf840b8c5987714162975e1308eac` | 2026-08-05T00:36:47-04:00 | none; n/a | 0/722 | SAFE branch cleanup | E1 tree 033e15cc847d11093131c18ec2b449082c1285e2 |
| `worktree-agent-a13566f6f2eae60c6` | `3612d4331921c1e05dfe885a8dcd5c857db606ea` | 2026-07-25T22:51:24-04:00 | none; n/a | 0/845 | SAFE branch cleanup | E1 tree eefd55cac3dcd26169e434eae68846d507afae6d |
| `worktree-agent-a144f20a6bab9803f` | `09a157620e25bfd9e0d8a9279787594012f692fb` | 2026-08-02T18:25:26-04:00 | none; n/a | 0/743 | SAFE branch cleanup | E1 tree dc62b9c256d92ff92f772532ac06106bd260e612 |
| `worktree-agent-a150542a25adbf68e` | `77b4a5033009c956f8eca557b920b401bdcbeb76` | 2026-08-08T11:04:19-04:00 | none; n/a | 0/647 | SAFE branch cleanup | E1 tree 37cf3e2aaddb86fa73713fc0c83b3b7549df579d |
| `worktree-agent-a1666e74f3763e0a7` | `1c04bc3ab3b072604400bc1425a193ff4f5b2172` | 2026-06-08T16:13:48-04:00 | none; n/a | 1/1019 | SAFE branch cleanup | E4 main d683fe8afed68ccb51b489faffe4d85045d66a18; patch 5b6dca5f1bf6501dbd3025216e7f2ad5a5da6e6d |
| `worktree-agent-a16b8c9e20f110454` | `36618be8e1644047fd2e6037e359fde567c5d889` | 2026-08-10T10:55:22-04:00 | none; n/a | 0/505 | SAFE branch cleanup | E1 tree 9ab5374a28bb3c05b91b4152f76b5c5dce507f47 |
| `worktree-agent-a1de9f7cdca7d4cc9` | `bb56c592bb76ce475e61f59ec9a53e06efbc82f9` | 2026-08-21T13:03:41-04:00 | none; n/a | 0/119 | SAFE branch cleanup | E1 tree 5c83d0b22d4d99d39f3b5759dc531ffe3a6d3b94 |
| `worktree-agent-a209b4b5` | `f93c76af239ea37b36e63f7d3ed4190a38b04eaf` | 2026-04-29T13:19:31-04:00 | none; n/a | 0/1079 | SAFE branch cleanup | E1 tree 21eb490403ad078c7f9c4656bb4fe1f81ac067b4 |
| `worktree-agent-a23ba874f1881182e` | `6da7747089ba1c8a77a8dd0232e2ef985bceebfc` | 2026-06-08T16:18:53-04:00 | none; n/a | 1/1019 | SAFE branch cleanup | E4 main 38b85777a87b12d41a51e62fb24ffe7a37392fcc; patch 6a74a9ccc56e6e4dbb4b85fbca7ab15bccbe9dc2 |
| `worktree-agent-a2472651` | `f93c76af239ea37b36e63f7d3ed4190a38b04eaf` | 2026-04-29T13:19:31-04:00 | none; n/a | 0/1079 | SAFE branch cleanup | E1 tree 21eb490403ad078c7f9c4656bb4fe1f81ac067b4 |
| `worktree-agent-a25635d5055222d04` | `31c77310f4c19a9574bfa8954dd9b5cb06599df7` | 2026-08-05T00:34:29-04:00 | none; n/a | 0/722 | SAFE branch cleanup | E1 tree 34a69a0ef1eeade44c29135963cb6d0915c83de9 |
| `worktree-agent-a2831e3434378f02f` | `ab9368f81aa580a007cc49c91240754206d3e1ec` | 2026-08-10T22:33:05-04:00 | none; n/a | 0/499 | SAFE branch cleanup | E1 tree 38f5709dd126a783f2e48010099061a1c942ed4e |
| `worktree-agent-a28505c47f2b4ed52` | `ffda9af2860eefd74534a1e52be4d7d50c727e7d` | 2026-08-01T16:32:31-04:00 | none; n/a | 0/782 | SAFE branch cleanup | E1 tree 81ca978d0aeb8e2251f1e8df5e52c25cb43ba96c |
| `worktree-agent-a28555e49939cb179` | `0eb1061b16c1bcf1ccdc6568ef4fc11cfe605f1b` | 2026-07-25T17:02:24-04:00 | none; n/a | 0/860 | SAFE branch cleanup | E1 tree c1a75b6c4e2e17331d337124948c5e91222fc674 |
| `worktree-agent-a28a3f476f5095e4e` | `deaa6b27fcf3d084b0ef1f3fa3c0af3b295d6db6` | 2026-08-05T00:36:29-04:00 | none; n/a | 0/722 | SAFE branch cleanup | E1 tree 9ac4934f6ca8402896962c4673cc4051fcbe6e38 |
| `worktree-agent-a28d45a9c473696b2` | `bcd64e8f15abf70a2c33d8b8589ceb61b85b5c29` | 2026-08-08T13:58:21-04:00 | none; n/a | 0/634 | SAFE branch cleanup | E1 tree 1333100ebbcf1f6b506be284f2f55eb373e2069a |
| `worktree-agent-a2953877` | `f93c76af239ea37b36e63f7d3ed4190a38b04eaf` | 2026-04-29T13:19:31-04:00 | none; n/a | 0/1079 | SAFE branch cleanup | E1 tree 21eb490403ad078c7f9c4656bb4fe1f81ac067b4 |
| `worktree-agent-a2a643a810416fc64` | `68920c3fa0c2195b6b9ea78c52e224dfadfc3f3c` | 2026-07-25T22:45:37-04:00 | none; n/a | 0/845 | SAFE branch cleanup | E1 tree 99005be637b23893f93fc67a54940f39a861966a |
| `worktree-agent-a2c3e26232f8d0fd3` | `6c008c31db12662fa8a453e7d88390920a1d42a6` | 2026-07-26T22:08:13-04:00 | none; n/a | 0/820 | SAFE branch cleanup | E1 tree 90ab9b0d3de200e562f3df5c9b6c3cdf427f8736 |
| `worktree-agent-a2eaddb5b4dcb9f75` | `0106aba4847ecc0a90241411390b2516d3f20fb8` | 2026-07-27T21:54:07-04:00 | none; n/a | 0/793 | SAFE branch cleanup | E1 tree 86a5099e1ef92181cffa77ed089698fcbc6c39ef |
| `worktree-agent-a302dd30809085cce` | `023f747a7f5d8fd7590fab82ff836b1f9d6706d8` | 2026-08-06T23:31:46-04:00 | none; n/a | 0/656 | SAFE branch cleanup | E1 tree e62d6729e95119e62447c5bdfdd3c6712553931b |
| `worktree-agent-a3079a842e541927e` | `62ff8d68221ce126f405e0fefbe9bb90b28cce45` | 2026-08-12T00:56:41-04:00 | none; n/a | 0/461 | SAFE branch cleanup | E1 tree 6e4972544cd95e64682ebd636f1876ac6c07d8cc |
| `worktree-agent-a30c874ee2bdc0aa2` | `048e918c7cea52acfc8ffddae089d7655c994b1d` | 2026-08-01T23:34:59-04:00 | none; n/a | 0/769 | SAFE branch cleanup | E1 tree bd9ee2438ba0ae70f013ea322ee11402615d910f |
| `worktree-agent-a323bd5a940b685f9` | `78d4bb399fb51ad1e10f1b9236debe84642f00a6` | 2026-08-03T23:27:13-04:00 | none; n/a | 0/736 | SAFE branch cleanup | E1 tree 343b3d5c74b21100e871c23b0b55e0bca1059627 |
| `worktree-agent-a3373f13` | `f93c76af239ea37b36e63f7d3ed4190a38b04eaf` | 2026-04-29T13:19:31-04:00 | none; n/a | 0/1079 | SAFE branch cleanup | E1 tree 21eb490403ad078c7f9c4656bb4fe1f81ac067b4 |
| `worktree-agent-a3528c7ae653aa236` | `f01ac9f80e8b2bdd8e799fc22ad9cd945229bde6` | 2026-08-21T15:11:30-04:00 | none; n/a | 0/115 | SAFE branch cleanup | E1 tree a745df8d3f5b9890748ad8c662d597c3d8cb5e9c |
| `worktree-agent-a368c8b0276754b90` | `e263490f46e38a6bb15754fda14f04db6f6a58d9` | 2026-07-25T14:05:14-04:00 | none; n/a | 0/865 | SAFE branch cleanup | E1 tree 62a30d58c771579c396232a5023eb8307ebcc593 |
| `worktree-agent-a36aaf8ad623b3be3` | `fc260dea52f39590f4e8b3ac100e83a0d4a5c424` | 2026-08-08T14:23:14-04:00 | none; n/a | 0/630 | SAFE branch cleanup | E1 tree 5c138af3a1ce940ac7811f37958044a854908dda |
| `worktree-agent-a37f0a74fe2ac8b03` | `b2bd07894a6dd67c25f21f0c2dc036332a75afc4` | 2026-08-03T23:14:28-04:00 | none; n/a | 0/736 | SAFE branch cleanup | E1 tree 0cd5e792349882fe9c3f0492f54448ae4f6a2c49 |
| `worktree-agent-a38bf08560c27a579` | `ec25407535357f4ddf16aa8f1f9a97bb1cbe6cdf` | 2026-07-27T11:59:46-04:00 | none; n/a | 0/799 | SAFE branch cleanup | E1 tree b62135956f331ad6a94a12a3e67219565f1487ac |
| `worktree-agent-a3ea3b1d38e084930` | `f7430c407fff14638ca771107efeee3466a71c0a` | 2026-08-20T18:09:20-04:00 | none; n/a | 0/150 | SAFE branch cleanup | E1 tree b383e524637e6664a823cb4320069fcf505ac442 |
| `worktree-agent-a3f099488f9a82ed1` | `572f5aa26d96e9fe75c1f643832ca824c827b921` | 2026-08-01T15:17:37-04:00 | none; n/a | 0/786 | SAFE branch cleanup | E1 tree 93b092b88e5738c23a6ec8030429422576307efd |
| `worktree-agent-a3f23e0d54808496f` | `b2127cee5d425cd6cda9806732d604cc91be1557` | 2026-06-08T16:12:02-04:00 | none; n/a | 1/1019 | SAFE branch cleanup | E4 main a3f178bba1ab51dc7ec40cfd80709d6df834e331; patch 46730f776ca35c7d1090616567bd16b61efe51c7 |
| `worktree-agent-a3ff0ef740318af5e` | `7758a13c437c1267b261535e80e659a44835e87e` | 2026-07-26T21:45:36-04:00 | none; n/a | 0/824 | SAFE branch cleanup | E1 tree 05c45d0f52104ca67e7d09a2374a65bcacfa3e81 |
| `worktree-agent-a4ab94c51456abb78` | `5ccffbe91fd4eb24601c7a677770824924976da0` | 2026-08-20T17:53:45-04:00 | none; n/a | 0/150 | SAFE branch cleanup | E1 tree 1171030ba16be6283b5300f3f7b92ff41ebc6c28 |
| `worktree-agent-a4b70cbf41800d5ca` | `57bd316aa980e7f76d760e2439751046d027a0d8` | 2026-08-06T23:24:57-04:00 | none; n/a | 0/657 | SAFE branch cleanup | E1 tree 732606df7aa7cb6dd8aaf2b5502f6a50b7b054fa |
| `worktree-agent-a4d512969948551d8` | `a1c1c26bfb7196734e944a62dd9820992914131e` | 2026-08-06T11:17:35-04:00 | none; n/a | 0/695 | SAFE branch cleanup | E1 tree 4eaccb1c67c3ed38a5ac82ad436a964ecfd5c240 |
| `worktree-agent-a5287232297d9fc77` | `d6e867d2cf3e45b5748856abfa3f865f56fc4aba` | 2026-07-26T21:54:54-04:00 | none; n/a | 0/820 | SAFE branch cleanup | E1 tree d0899a8566ab5baff46e78745e3894abe4a744fa |
| `worktree-agent-a52b467fa9f45f7da` | `c198e61253f71c908462e267803425bb02f561f7` | 2026-08-01T16:35:05-04:00 | none; n/a | 0/782 | SAFE branch cleanup | E1 tree 8f07a43897c67de7481eaf851cc3be0070151b78 |
| `worktree-agent-a5391ce09098b9c73` | `4f3b1fe63876ce664722131ff873a04ef759d30a` | 2026-07-25T10:47:54-04:00 | none; n/a | 0/869 | SAFE branch cleanup | E1 tree 9ddd09c3cdc87e8205c130ebd94c41df4533d93d |
| `worktree-agent-a53fe1fe4f7a84b07` | `715017882b6fbb79f3fd9f86bf97796ea3f02b24` | 2026-08-08T11:02:48-04:00 | none; n/a | 0/647 | SAFE branch cleanup | E1 tree 3fecd49ee4d940e2648e41af7ef908d910356533 |
| `worktree-agent-a54190da471e3ddf9` | `a3152d48b66c8f28b953cf6d46adfa96a071acc2` | 2026-08-06T11:21:55-04:00 | none; n/a | 0/695 | SAFE branch cleanup | E1 tree d9a8e7e51ddca9b77d810fac824ab6c142df2e6a |
| `worktree-agent-a556441520fcd3c9c` | `2b8eccaf636217155f4cd94f3046d7cd5ee0d280` | 2026-08-01T15:32:51-04:00 | none; n/a | 0/786 | SAFE branch cleanup | E1 tree 34432c49b8f076fc8c9e267101eb70fe68981be9 |
| `worktree-agent-a55e79db9100f2290` | `87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5` | 2026-04-30T23:34:23-04:00 | none; n/a | 0/1056 | SAFE branch cleanup | E1 tree e5533e4907df0480314ff1f963619d9f481c7c8e |
| `worktree-agent-a59705cabd6f6c62d` | `87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5` | 2026-04-30T23:34:23-04:00 | none; n/a | 0/1056 | SAFE branch cleanup | E1 tree e5533e4907df0480314ff1f963619d9f481c7c8e |
| `worktree-agent-a5a06a944cf8dedbd` | `f5e8ae5f76af54b98c06dc7b52c3eeade6f6c3d0` | 2026-07-20T15:50:14-04:00 | none; n/a | 0/883 | SAFE branch cleanup | E1 tree 2271efd7988006ae782bc04668a639dc662c1abf |
| `worktree-agent-a5c128404456a4b8e` | `ba78631e1562ddcf45ad6358ce047289bcd342ae` | 2026-08-02T00:28:57-04:00 | none; n/a | 0/758 | SAFE branch cleanup | E1 tree e4178d2e5111f926a72bb3202e63f392f3fc1ad9 |
| `worktree-agent-a5c3d72a8892d8be8` | `b5242ea33c47b90353a3adc4e554d4ed80a94746` | 2026-08-03T23:12:31-04:00 | none; n/a | 0/736 | SAFE branch cleanup | E1 tree ae37cbe3bf01dafa81497b7293b7864812b5ebf7 |
| `worktree-agent-a5c985a3fe89fb27d` | `54e199ea22450e77563959de266ac79534bbc2dd` | 2026-08-01T23:29:21-04:00 | none; n/a | 0/782 | SAFE branch cleanup | E1 tree a4ec2962a420813ca2fed48732fc601e72ff2599 |
| `worktree-agent-a5cd4e9707c993055` | `87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5` | 2026-04-30T23:34:23-04:00 | none; n/a | 0/1056 | SAFE branch cleanup | E1 tree e5533e4907df0480314ff1f963619d9f481c7c8e |
| `worktree-agent-a5dbf1a5a83fba809` | `2e4ca17aae1421f2f032c616dd28a4fd8c32ecbd` | 2026-08-02T00:38:45-04:00 | none; n/a | 0/758 | SAFE branch cleanup | E1 tree 95507406cec77e653911aeef7d68c525157ea3ea |
| `worktree-agent-a60b48a57928d5895` | `eb9c1dee7029a301d4bda535f12b380b8f80ddbc` | 2026-08-21T01:58:56-04:00 | none; n/a | 0/124 | SAFE branch cleanup | E1 tree 23391a2d0d7d5655e703015b0ccc8708198271c2 |
| `worktree-agent-a6190fadbdb2acebe` | `87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5` | 2026-04-30T23:34:23-04:00 | none; n/a | 0/1056 | SAFE branch cleanup | E1 tree e5533e4907df0480314ff1f963619d9f481c7c8e |
| `worktree-agent-a651d045` | `4da6011312b0dc0d446cbc58694e628d0ea9bdb3` | 2026-04-29T15:39:57-04:00 | none; n/a | 1/1079 | HOLD unresolved content | E5 1 unmatched commits; 3/3 branch-touched paths differ |
| `worktree-agent-a670c42a14aa79fba` | `33636ec12a9a6ea02bb434a6b49097fae0dfe0a8` | 2026-08-05T00:39:52-04:00 | none; n/a | 0/722 | SAFE branch cleanup | E1 tree a8960e84fa93820c005c57d878123963feea3d4e |
| `worktree-agent-a6a9a0b3a6b20d104` | `93229e3d09baeb2a86059769c166a8220436a0f4` | 2026-07-25T22:34:01-04:00 | none; n/a | 0/845 | SAFE branch cleanup | E1 tree e60230fa34b25f8e384daeb36bc102f9ce595aeb |
| `worktree-agent-a6f676d19f96310cd` | `c22e7311d2bc3a575077a69ac444ce24ffb640ab` | 2026-05-21T10:35:55-04:00 | none; n/a | 0/1036 | SAFE branch cleanup | E1 tree c8f866dce00de3b9d79d3d31de618e7ae6106995 |
| `worktree-agent-a6ffa39f8ba6a8814` | `5ae45f2bb31cbef0a540ea106b9ee3343bfa8c37` | 2026-07-27T21:35:28-04:00 | none; n/a | 0/793 | SAFE branch cleanup | E1 tree 238a5b8e0b9418557efa1e491674b48144bcfdee |
| `worktree-agent-a7071f4335335f4f5` | `332d9b551d449a48a98535d85dea25eb4a249fb5` | 2026-07-25T19:11:50-04:00 | none; n/a | 0/855 | SAFE branch cleanup | E1 tree 5e8946fae0c84b234380534d89491475e3b3f603 |
| `worktree-agent-a717758e4fb09729a` | `53bd19f696f7dfd3be01fef8aea248bba49c80d5` | 2026-08-11T17:09:19-04:00 | none; n/a | 0/476 | SAFE branch cleanup | E1 tree c4a7990c8805ac6a7495a8e403f3dcb5ffed651c |
| `worktree-agent-a729a704` | `76c4ae0e2d992cd828ce56fd3bae76cde89519cb` | 2026-04-29T15:24:11-04:00 | none; n/a | 1/1079 | HOLD unresolved content | E5 1 unmatched commits; 1/1 branch-touched paths differ |
| `worktree-agent-a745688e80fa5caa9` | `01962ce656c3f9f461bf259b0b67d5cca167a50f` | 2026-08-02T00:29:44-04:00 | none; n/a | 0/758 | SAFE branch cleanup | E1 tree 2699f079128fd8069847136597693a81759130c2 |
| `worktree-agent-a75a01fb` | `f93c76af239ea37b36e63f7d3ed4190a38b04eaf` | 2026-04-29T13:19:31-04:00 | none; n/a | 0/1079 | SAFE branch cleanup | E1 tree 21eb490403ad078c7f9c4656bb4fe1f81ac067b4 |
| `worktree-agent-a762a0a5e278cb792` | `6577668859c6d97f2412eb2f856ec9dd4d01777b` | 2026-08-05T01:09:56-04:00 | none; n/a | 0/722 | SAFE branch cleanup | E1 tree 3157d1640203f88e3064f539006aab679de63669 |
| `worktree-agent-a77c43dcc4f3b0197` | `03e3e38c91039cb57f5703323a729c04a4ff2225` | 2026-07-25T19:24:09-04:00 | none; n/a | 0/855 | SAFE branch cleanup | E1 tree 12c5d5ebb2a38ab97478981d6e79fd43437db974 |
| `worktree-agent-a781bda1e318a3477` | `6f2ac9566a99fc921f9cee022643e77e8c9ccf40` | 2026-07-27T21:38:31-04:00 | none; n/a | 0/793 | SAFE branch cleanup | E1 tree b38786cb2fb11047ac02378c91db1210f85e2a96 |
| `worktree-agent-a795927256b2f29e7` | `19ccf9e811782064d66eea65b070d88880cffb39` | 2026-08-08T11:14:06-04:00 | none; n/a | 0/647 | SAFE branch cleanup | E1 tree 76e4cbb0d12bd45a2deeda73aa2fed835ce6081d |
| `worktree-agent-a7a973b4596ade6b1` | `bcbc46f2e5576b7f3e5e5868ae38b94fba3694e2` | 2026-07-20T14:19:02-04:00 | none; n/a | 0/883 | SAFE branch cleanup | E1 tree ee457b4661a86d26e6b43608d99bab4c23f68b47 |
| `worktree-agent-a7bed877f805980b0` | `0a7f791abb96b79fc361ce5cd4fe10b621143595` | 2026-08-20T17:39:20-04:00 | none; n/a | 0/151 | SAFE branch cleanup | E1 tree 649de274384651daf882c86c6fc032a0beba4eda |
| `worktree-agent-a7e7c39e9775a0f73` | `0bc98ffc868e964aa212de0007e85cb683a8c4ed` | 2026-08-06T01:42:57-04:00 | none; n/a | 0/700 | SAFE branch cleanup | E1 tree ee83b67c939e8b05248b550f0e19227bb9316fce |
| `worktree-agent-a7f0838e43f31b457` | `affd0869a4bbaccc69b4dd8a0e574560ab0b856b` | 2026-08-02T00:01:34-04:00 | none; n/a | 0/758 | SAFE branch cleanup | E1 tree 1a1a8ebfce323024aa1b9842747170720eec8859 |
| `worktree-agent-a8194dbbf32434db9` | `87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5` | 2026-04-30T23:34:23-04:00 | none; n/a | 0/1056 | SAFE branch cleanup | E1 tree e5533e4907df0480314ff1f963619d9f481c7c8e |
| `worktree-agent-a8213859c9ad5c121` | `a8898a7a7d9cc67f5cf3b81d451c64ed698a86cf` | 2026-07-25T22:43:32-04:00 | none; n/a | 0/844 | SAFE branch cleanup | E1 tree 340b10d3c7eb76d35c20c8809e7e8913f3ef5518 |
| `worktree-agent-a838fcfecbdc8645b` | `4795a219030523cb83614b241548ee1ef0a7ec9d` | 2026-08-03T23:12:09-04:00 | none; n/a | 0/736 | SAFE branch cleanup | E1 tree 95feb85048a16b9bac6b5126bce333aaa47a7164 |
| `worktree-agent-a840269e071c723d0` | `ab9368f81aa580a007cc49c91240754206d3e1ec` | 2026-08-10T22:33:05-04:00 | none; n/a | 0/499 | SAFE branch cleanup | E1 tree 38f5709dd126a783f2e48010099061a1c942ed4e |
| `worktree-agent-a874d90a1a9da98d0` | `19dc31b40529ef1c828ed8e52d6839aa817d2751` | 2026-08-08T09:59:35-04:00 | none; n/a | 0/652 | SAFE branch cleanup | E1 tree 566cb9f009ce7315f82e4cd19ecbb7dc17833726 |
| `worktree-agent-a8c67b5203e41c78e` | `53bd19f696f7dfd3be01fef8aea248bba49c80d5` | 2026-08-11T17:09:19-04:00 | none; n/a | 0/476 | SAFE branch cleanup | E1 tree c4a7990c8805ac6a7495a8e403f3dcb5ffed651c |
| `worktree-agent-a8e7a7cd54b0167e9` | `5b2dc5f8b3515cbe231bfe24d3fea22bf1cd17e8` | 2026-07-26T22:00:24-04:00 | none; n/a | 0/820 | SAFE branch cleanup | E1 tree 2017f339cd2715115a85e479082e79eedc5d7698 |
| `worktree-agent-a8f35b1a442cb2147` | `eb9c1dee7029a301d4bda535f12b380b8f80ddbc` | 2026-08-21T01:58:56-04:00 | none; n/a | 0/124 | SAFE branch cleanup | E1 tree 23391a2d0d7d5655e703015b0ccc8708198271c2 |
| `worktree-agent-a9064f78118fe3182` | `bcc54af21b97bc723890f9684fbff083b72cf441` | 2026-07-26T22:01:45-04:00 | none; n/a | 0/814 | SAFE branch cleanup | E1 tree e85618107945faf41d2cc73e05b142aa6e904f4e |
| `worktree-agent-a93ea1c02c0aa67a6` | `4d7184aeaec8f2a768406b4872b4daede1228b17` | 2026-07-26T21:42:58-04:00 | none; n/a | 0/825 | SAFE branch cleanup | E1 tree 1bbb8ce5fcd7e8e8d35b1c643e24f17d0c7f6439 |
| `worktree-agent-a94f79872cf3c2956` | `da09db224cc3ecdd9d3a23ae2cc405e56ee9cd67` | 2026-08-06T22:02:29-04:00 | none; n/a | 0/658 | SAFE branch cleanup | E1 tree 25c90b861eab486bf6609e10df127062d10d75d6 |
| `worktree-agent-a9929996116eab11d` | `5ec0f6a4119ce23a0a4ce4790d839e173d2514d3` | 2026-08-06T17:41:12-04:00 | none; n/a | 0/663 | SAFE branch cleanup | E1 tree c61f8a37bee985f20d328d28e8ddf49c3216c8f4 |
| `worktree-agent-a9a2270cdf24df420` | `53bd19f696f7dfd3be01fef8aea248bba49c80d5` | 2026-08-11T17:09:19-04:00 | none; n/a | 0/476 | SAFE branch cleanup | E1 tree c4a7990c8805ac6a7495a8e403f3dcb5ffed651c |
| `worktree-agent-a9b33518` | `1485c1727a5b630932ba806fc874d0af2f3b3fbc` | 2026-04-29T15:24:12-04:00 | none; n/a | 1/1079 | HOLD unresolved content | E5 1 unmatched commits; 2/2 branch-touched paths differ |
| `worktree-agent-a9b538e94beefb1bb` | `fefe72fe5d6cd72e71b7fbc6b7f1ec0484f22821` | 2026-08-07T00:43:04-04:00 | none; n/a | 0/653 | SAFE branch cleanup | E1 tree 4b060a7f3f4099436c79644a594930a010ef7451 |
| `worktree-agent-a9c4c705ebb53fc71` | `60aa45721ae5419a218027674471adedf46aa5df` | 2026-09-01T17:43:16-04:00 | none; n/a | 1/19 | HOLD unresolved content | E5 1 unmatched commits; 4/4 branch-touched paths differ |
| `worktree-agent-a9e7150a335178db6` | `9e7dfd4ca6a1b2f4608d38eebac4b6940919234b` | 2026-08-02T18:26:52-04:00 | none; n/a | 0/743 | SAFE branch cleanup | E1 tree 06a6b974d4d433b62a95b2dbd0ca0106a6096e9a |
| `worktree-agent-aa22a939b267fbed4` | `cce3895fcaafec47dd4a1c4dd9b8588fec9cedcb` | 2026-08-24T00:33:21-04:00 | none; n/a | 0/80 | SAFE branch cleanup | E1 tree f7a12bdadc9baa706d2e75b209ceefbffaa3b41d |
| `worktree-agent-aa44d177d8f47b9fc` | `5b01e397a152e62b9b4d0101d05c989fc49d512d` | 2026-07-25T17:08:29-04:00 | none; n/a | 0/860 | SAFE branch cleanup | E1 tree 772b5324437970d230f1bc783bb60a6f366eb88e |
| `worktree-agent-aa51708f12ba44358` | `67b4a439fd59bca4080af1ac424d8928fe5f0c9c` | 2026-08-01T23:29:34-04:00 | none; n/a | 0/782 | SAFE branch cleanup | E1 tree 91aa6f274eca6f297930d619d64dc15d68a5fe45 |
| `worktree-agent-aa9087fcaaa04e2ac` | `ab9368f81aa580a007cc49c91240754206d3e1ec` | 2026-08-10T22:33:05-04:00 | none; n/a | 0/499 | SAFE branch cleanup | E1 tree 38f5709dd126a783f2e48010099061a1c942ed4e |
| `worktree-agent-aa9f436167ca0131a` | `2e3f61f5096a9e53f172bbf886f0a8ca42054bed` | 2026-08-05T01:04:32-04:00 | none; n/a | 0/722 | SAFE branch cleanup | E1 tree 436a01527d3e1d768f03292d544e2e8ad7255acc |
| `worktree-agent-aab1fb2eaf05f2174` | `c0e99ba4e324e9bee2bc3a8d8e9c1c8ea8029d69` | 2026-08-02T18:28:56-04:00 | none; n/a | 0/743 | SAFE branch cleanup | E1 tree 90a2af42ca33586df116fdc10fd363bd1da4bd77 |
| `worktree-agent-aac10f493d748fa5c` | `fbad804ac30324c280313fcd593a10c6f256b19d` | 2026-08-01T23:38:19-04:00 | none; n/a | 0/769 | SAFE branch cleanup | E1 tree ad85fa2506fa93ad14dcd45660165f08cdab7ffd |
| `worktree-agent-aacfbf4446690cbea` | `3b785f9d4ec172e3f30bb16e5d445c358ca85b47` | 2026-08-01T23:33:07-04:00 | none; n/a | 0/782 | SAFE branch cleanup | E1 tree 69cf43ed5fd77afda0be195077c77b7c86d00382 |
| `worktree-agent-ab0fb0a7` | `f93c76af239ea37b36e63f7d3ed4190a38b04eaf` | 2026-04-29T13:19:31-04:00 | none; n/a | 0/1079 | SAFE branch cleanup | E1 tree 21eb490403ad078c7f9c4656bb4fe1f81ac067b4 |
| `worktree-agent-ab1657e4739bfb5ad` | `22d3ad872bc71cd02fe16e3cd3b97c08b229d38a` | 2026-08-08T11:11:16-04:00 | none; n/a | 0/647 | SAFE branch cleanup | E1 tree 764867741196fe0c13054040a00c103064551587 |
| `worktree-agent-ab2f89d27bbf14bde` | `4a4b6718f8d69c692138a1fdc7e41b5abeb77c89` | 2026-08-12T22:00:08-04:00 | none; n/a | 0/426 | SAFE branch cleanup | E1 tree 51726257ba5ce728e88a6a8d3a6f1c6d38d1b2dc |
| `worktree-agent-ab454ff44a5679193` | `ed0c4539207ec34ef428cff45bfb7ee64490ec56` | 2026-08-09T19:22:35-04:00 | none; n/a | 0/551 | SAFE branch cleanup | E1 tree c2e24e5a7c5eaa4db2aa4ad28a2f218b1bd90fd9 |
| `worktree-agent-ab5ed8ed` | `7730729b6cb6f58f81c65f8e36946320fb1efe23` | 2026-04-29T15:22:56-04:00 | none; n/a | 1/1079 | HOLD unresolved content | E5 1 unmatched commits; 1/1 branch-touched paths differ |
| `worktree-agent-ab7db2284f1a23a25` | `53bd19f696f7dfd3be01fef8aea248bba49c80d5` | 2026-08-11T17:09:19-04:00 | none; n/a | 0/476 | SAFE branch cleanup | E1 tree c4a7990c8805ac6a7495a8e403f3dcb5ffed651c |
| `worktree-agent-ab82847f1df895787` | `d94988a86d635cbeaebfcbf11af4e97c2260d83b` | 2026-08-06T19:45:35-04:00 | none; n/a | 0/662 | SAFE branch cleanup | E1 tree 35b600d7d67d9684d737e6ce96fac38f77318803 |
| `worktree-agent-abf2d752f509e445b` | `0d8d7bbed9b204704b4f9a02c996cc6a268b7472` | 2026-08-15T20:36:02-04:00 | none; n/a | 0/366 | SAFE branch cleanup | E1 tree 4d3499937b60261537c1ac48a662c027168f3e97 |
| `worktree-agent-abf3b3a8687622967` | `0e997243358ea5db090a4fe44bbef9d7d7902e09` | 2026-08-08T14:06:25-04:00 | none; n/a | 0/643 | SAFE branch cleanup | E1 tree 04b98b959ddc600c78e4c5589bc899e0c988828b |
| `worktree-agent-ac1556ef` | `f93c76af239ea37b36e63f7d3ed4190a38b04eaf` | 2026-04-29T13:19:31-04:00 | none; n/a | 0/1079 | SAFE branch cleanup | E1 tree 21eb490403ad078c7f9c4656bb4fe1f81ac067b4 |
| `worktree-agent-ac3579d0fd8f1d2d8` | `2b7eb33f4298ed700eff4f8d9c8c9645170b4d84` | 2026-06-08T16:11:51-04:00 | none; n/a | 1/1019 | HOLD dirty worktree | E4 main 9aef5e1fbb4b50fb22e1abdb022643a455122021; patch 90ad401c6615d2a1b0060c17bbbb92a04442a69e |
| `worktree-agent-ac51ccfd88e45a7e0` | `8b44a5db9893cb768102b316fa55e7a28166ef09` | 2026-08-08T11:14:45-04:00 | none; n/a | 0/647 | SAFE branch cleanup | E1 tree f5d6f85c9a708966b822ef339e4a2be25c065db4 |
| `worktree-agent-ac625c4f4e8d21b0e` | `fbd556116724e10726899e43a4d7d084f96f5669` | 2026-07-27T11:55:18-04:00 | none; n/a | 0/799 | SAFE branch cleanup | E1 tree e71284b890bfbff9f8cb2a0f0cfd2128c0279c5e |
| `worktree-agent-ac67214a25c77896d` | `d89a4ad3b82cf194b62b15be7774b58482f252b2` | 2026-08-03T23:26:06-04:00 | none; n/a | 0/736 | SAFE branch cleanup | E1 tree 8ad13a93521cad200d74a9e4c296e4a20cd0bb80 |
| `worktree-agent-ac81596c5b45c68c9` | `18f84288d9ba126e46c834ab34ba9a000cb820ba` | 2026-08-08T11:15:19-04:00 | none; n/a | 0/647 | SAFE branch cleanup | E1 tree 5c2f0924afbba7778c8992b1bcbd23175f129769 |
| `worktree-agent-ac919199823a00f48` | `d44200f23f9f4cd65633f3ff5407098d31c2b334` | 2026-07-20T13:49:35-04:00 | none; n/a | 0/884 | SAFE branch cleanup | E1 tree 813ce6e2911677349247ef10d2327975e7d5a472 |
| `worktree-agent-ac98e8e8cf1e59684` | `ea19d4b75cc9de1bf33d48d615678b8bd8356715` | 2026-08-09T22:31:25-04:00 | none; n/a | 0/531 | SAFE branch cleanup | E1 tree 9171318b1ff283af3b3cada781117ca267adb8c0 |
| `worktree-agent-acc5272eb7eb24e4e` | `0e6cffa966f4edbcd5ac49ac5b47ab7e0d91aa44` | 2026-08-01T23:36:28-04:00 | none; n/a | 0/782 | SAFE branch cleanup | E1 tree 757601415a32afac725ad0c89fb7ac489ba6c418 |
| `worktree-agent-acce1e33b7aef0abe` | `e1309beb8437bfb2b0e8a34446c86a86efc44e74` | 2026-08-02T18:14:27-04:00 | none; n/a | 0/745 | SAFE branch cleanup | E1 tree 25b058c164cd2ecafecfb985e18eedac275f0b4d |
| `worktree-agent-acfd5ca9` | `f93c76af239ea37b36e63f7d3ed4190a38b04eaf` | 2026-04-29T13:19:31-04:00 | none; n/a | 0/1079 | SAFE branch cleanup | E1 tree 21eb490403ad078c7f9c4656bb4fe1f81ac067b4 |
| `worktree-agent-acfebfb1bbb7e02af` | `f65bab75adf3a949c82402a4f0c6767166bcb142` | 2026-08-11T11:19:09-04:00 | none; n/a | 0/478 | SAFE branch cleanup | E1 tree 789ea1f8df9ead38ea4dd664dd0c6cdca4324db6 |
| `worktree-agent-ad5be481f59c206d2` | `0848edd907c3bf5bf0982e9bf28a651e11e88ea8` | 2026-08-01T16:31:43-04:00 | none; n/a | 0/782 | SAFE branch cleanup | E1 tree 090e60635637b78f0fb2a6c6c1c6e357ebc00479 |
| `worktree-agent-ad7046bc` | `90cb01edde8474646ceaaf74ef8dceefc0cc8a43` | 2026-04-29T15:25:13-04:00 | none; n/a | 1/1079 | HOLD unresolved content | E5 1 unmatched commits; 2/2 branch-touched paths differ |
| `worktree-agent-ad81d6d15fc57b088` | `0dd3b0e4d34dcea27e0568b74932c8a82e4babc6` | 2026-08-06T15:24:39-04:00 | none; n/a | 0/678 | SAFE branch cleanup | E1 tree 67ba931456af90d02b32d78231ebeb56697d7140 |
| `worktree-agent-ad8eb8ca` | `f93c76af239ea37b36e63f7d3ed4190a38b04eaf` | 2026-04-29T13:19:31-04:00 | none; n/a | 0/1079 | SAFE branch cleanup | E1 tree 21eb490403ad078c7f9c4656bb4fe1f81ac067b4 |
| `worktree-agent-adb355036fe847189` | `be56567ec52efe4a92647bfd0b2d200e78c251bb` | 2026-08-06T21:03:43-04:00 | none; n/a | 0/659 | SAFE branch cleanup | E1 tree b16614f21e67708645757cab35e19c2468e2fa5d |
| `worktree-agent-adc544906c182a442` | `7633561ec801e9a521e65ebb30dd22bb6f02f532` | 2026-06-08T16:10:52-04:00 | none; n/a | 1/1019 | SAFE branch cleanup | E4 main c4f8bf77499b9c51e75d4981f207a7810c606a41; patch cb695aa905bd572b82c09e37d1cdbd0dfc8150b0 |
| `worktree-agent-ade0db7c` | `ff9f88b889bb94d8759cf848854cd0e01234f7fd` | 2026-04-29T15:22:43-04:00 | none; n/a | 1/1079 | HOLD unresolved content | E5 1 unmatched commits; 1/1 branch-touched paths differ |
| `worktree-agent-adec00ae3a2e7dccc` | `16b1dcb3fe9b4d4e20bc18eb9fc4dfb2c9c20510` | 2026-08-10T02:54:25-04:00 | none; n/a | 0/510 | SAFE branch cleanup | E1 tree 0326294de4f9c79b605e74db1950cd2a091a7663 |
| `worktree-agent-adfd16bf190678bcd` | `c5f6f9c4aa274acac261d7fd77fb82d6db3854cb` | 2026-08-03T23:19:53-04:00 | none; n/a | 0/736 | SAFE branch cleanup | E1 tree f4bacaa16557b3d52ad2e6adb181241f4527959f |
| `worktree-agent-ae06d26a381e039cc` | `66cd2eac050c02fd005a9b13e7d1b9cf072b6cea` | 2026-05-20T19:16:12-04:00 | none; n/a | 0/1053 | SAFE branch cleanup | E1 tree 547ed15e6843b09c31cc393921fd9a1d8d81efa7 |
| `worktree-agent-ae2f8898ea0b703a7` | `e297ea860f72d91d1bb567943143834bb5ab5551` | 2026-08-06T01:29:46-04:00 | none; n/a | 0/700 | SAFE branch cleanup | E1 tree f2d4e13fda448935724f2f33eab1598b36913cc7 |
| `worktree-agent-ae3050bc4e4ca4e49` | `87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5` | 2026-04-30T23:34:23-04:00 | none; n/a | 0/1056 | SAFE branch cleanup | E1 tree e5533e4907df0480314ff1f963619d9f481c7c8e |
| `worktree-agent-ae33eec5a00d24264` | `52be577e7320b69116215b57505d3c076c2577c4` | 2026-07-25T13:20:05-04:00 | none; n/a | 0/865 | SAFE branch cleanup | E1 tree 35275ea623b8938a8f1c978b88d30cc94a2e3db9 |
| `worktree-agent-ae9d48bf5dc036db8` | `618a3d18313b347c234b847eec3f5d780bf6a6dd` | 2026-07-23T10:00:19-04:00 | none; n/a | 0/876 | SAFE branch cleanup | E1 tree 5f1debcccbb11956c122a70a9ba815c371d58c86 |
| `worktree-agent-aec3f38caa8be282f` | `2d6d4f7940f751481f336e473b1e7e3278b8fa4d` | 2026-06-08T16:13:52-04:00 | none; n/a | 1/1019 | SAFE branch cleanup | E4 main 031099a81df16476bff66aba2efd530029953fa2; patch fc667cc79b9b8a6247995c685780ef5aed3f1956 |
| `worktree-agent-aece02885ca19e959` | `69a8ff8e4a17f941f318f5cd9936a58090696e28` | 2026-08-05T01:08:37-04:00 | none; n/a | 0/712 | SAFE branch cleanup | E1 tree 271dbc1f7e3d63408fe21000f074ba9ec4fb0194 |
| `worktree-agent-aecf5fa60c4ffcaea` | `87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5` | 2026-04-30T23:34:23-04:00 | none; n/a | 0/1056 | SAFE branch cleanup | E1 tree e5533e4907df0480314ff1f963619d9f481c7c8e |
| `worktree-agent-aef0655458c9f55b9` | `db007c311a987c35d27b306ec051565fc8da79ab` | 2026-08-06T11:40:46-04:00 | none; n/a | 0/692 | SAFE branch cleanup | E1 tree d481e2bce1ed7c38987e0a4e6545a46aabd44bcf |
| `worktree-agent-af4b9c0445be5f5a5` | `4ac6673690ad50408b78bcf3cc87ab3a635f05bd` | 2026-08-02T00:35:16-04:00 | none; n/a | 0/758 | SAFE branch cleanup | E1 tree 63e094fe715eba46ff9842f6bee8454b8cc887f5 |
| `worktree-agent-af95ea98f982612d6` | `451d2ebd714033a3b1f6bba3fc1b939f9d086efb` | 2026-08-20T21:33:20-04:00 | none; n/a | 0/126 | SAFE branch cleanup | E1 tree 697c439818ceb3faf6cfb55b727904a5d690409e |
| `worktree-agent-afa591a17c448320e` | `676f96d1c4ccf4d75094d4a0dd2d015a3e1b58d0` | 2026-08-08T11:09:53-04:00 | none; n/a | 0/647 | SAFE branch cleanup | E1 tree 46b45723706f8cc9486a6091323d9a0cc60fb03d |
| `worktree-agent-afa6d1c4926e46d77` | `e5df03e6b8e3754a3c6f8a62dc4797b5b9773a21` | 2026-08-06T17:30:47-04:00 | none; n/a | 0/667 | SAFE branch cleanup | E1 tree b916830e3cbb37e9e8cd6891a215e1265773d9a0 |
| `worktree-agent-afae520a937d45e74` | `e98560a698804aaacbbe07fbf2bd4d86bb1aeb9f` | 2026-08-05T15:08:50-04:00 | none; n/a | 0/705 | SAFE branch cleanup | E1 tree bccb9ac8fee00eacc7e5e6a36fad3223d663a219 |

## Complete remote-tracking inventory

The 98 real origin heads were verified live. `origin/HEAD` is symbolic; `agent372/composite` has no configured remote and is an orphan tracking ref, not a remote deletion target. Local and remote tips can differ; each row carries its own exact SHA and proof.

| Tracking ref | Tip SHA | Commit date | Main A/B | Verdict | Content evidence |
|---|---|---|---|---|---|
| `agent372/composite` | `ba4a6ad1446acddbac468d94e52faf38036b46c8` | 2026-08-20T20:58:25-04:00 | 0/136 | HOLD orphan remote-tracking ref; no configured agent372 remote | E1 tree f6320ae6ce12803d0ebff47db9385319881c66bd |
| `origin/HEAD` | `606e512cd87f692eced3b92ccadb4f0192ea3449` | 2026-09-03T14:18:19-04:00 | 0/0 | Alias; retain | E1 tree ad663e32c2049ad5a46bdfaac38aa245d98b1aa6 |
| `origin/analytics-300` | `0b6487163b14990af330612a6b1818ca31da6d2d` | 2026-08-12T09:59:30-04:00 | 20/460 | SAFE branch cleanup | E4 main 5139b459ea2b1594ab0c85a4881931bdeca870bf; patch 9ca5cbd20a2b71921d14142274498ce5def277e6 |
| `origin/audit/knockout-waterfall-v2` | `290b3ed94d65df782fd9bd1f805b7a343651a531` | 2026-08-22T11:25:20-04:00 | 1/107 | HOLD unresolved content | E5 1 unmatched commits; 2/2 branch-touched paths differ |
| `origin/audit/perf-optimization` | `71ed60b2edf1e88a6e64a99ad6e09ddfb2cddf34` | 2026-06-07T12:22:11-04:00 | 1/1030 | HOLD unresolved content | E5 1 unmatched commits; 40/44 branch-touched paths differ |
| `origin/chore/commit-docs-and-claude-tree` | `e00940d8c4ce36be2d082f985c76c99bb2c49e11` | 2026-05-21T10:18:26-04:00 | 1/1048 | SAFE branch cleanup | E4 main 56fcf91d79623087f1a4cfefecc11759cef3cec8; patch 6757bf3d0530628f05e1e8653cb7de38eeae4f2e |
| `origin/chore/eas-submit-ascappid` | `8353ec3075826d6db89efbf4231e86d137450959` | 2026-05-20T20:22:26-04:00 | 1/1051 | SAFE branch cleanup | E3 1 changed paths equal current main |
| `origin/chore/session-wrapup` | `4340b60473bc1ab6d39fd80f3d312ad4a6e8c778` | 2026-08-20T21:24:57-04:00 | 0/127 | SAFE branch cleanup | E1 tree 697c439818ceb3faf6cfb55b727904a5d690409e |
| `origin/claude/api-audit-redundancies-9a6075` | `b8c8dd598e5d5302b240a4fc3e78b9265bd76ede` | 2026-09-03T12:19:36-04:00 | 12/5 | SAFE branch cleanup | E4 main c2775fe03fcd6d47824e17fa444681b0cc3628c0; patch e8684e5ac6949c9dbb5f801ec8663330cb4cded3 |
| `origin/claude/busy-swartz-521ff5` | `18f15f7ad36ca988ef364fc4d0041218f7313a52` | 2026-07-10T02:58:13-04:00 | 0/997 | SAFE branch cleanup | E1 tree 544630af4d5d18e72ee6fb412f4e192e49eb6b5e |
| `origin/claude/finder-gap-analysis-writeback` | `3f5af51c3e496c48a958171425933177cf9f9691` | 2026-08-31T17:44:09-04:00 | 1/22 | SAFE branch cleanup | E4 main 2ceff988b41268753546d284466f070e3d0c3bca; patch 308c271a368e077e5bcc920a42d7d36edbca21d4 |
| `origin/claude/ftf-file-continuation-c9185e` | `5adc848474f4b766101f2f1d56127577d066ab88` | 2026-08-28T12:44:02-04:00 | 3/52 | SAFE branch cleanup | E4 main 80f08db600fd1d0cc8f8289ca558177957f04e24; patch d2e3b8190f62deaca4802b1a56f29c912606fcee |
| `origin/claude/ledger-correction-partner-summary` | `ba8e84d17ffeb63b6ec0d3e7f2f707bc9ba912b8` | 2026-08-27T11:42:34-04:00 | 1/53 | HOLD open PR #223 | E5 1 unmatched commits; 1/1 branch-touched paths differ |
| `origin/claude/new-user-feedback-06dabd` | `cd1d243bfa59d4291729730166b5a16d167dfde3` | 2026-09-03T13:56:09-04:00 | 14/5 | HOLD open PR #274 | E5 11 unmatched commits; 45/45 branch-touched paths differ |
| `origin/claude/new-user-feedback-55320e` | `f7833d566f9fddf1c320e7f217a843ce7435a1e0` | 2026-08-24T16:25:22-04:00 | 28/77 | SAFE branch cleanup | E4 main fa945925d995e8895e78285661f792f0c12f044d; patch 9670267b2ad419571af92c007a7e56b6c19ae2ea |
| `origin/claude/new-user-feedback-d4c47d` | `62bd658f65639772a8ca70f92bb74f769b1f2389` | 2026-08-22T00:11:20-04:00 | 2/108 | SAFE branch cleanup | E4 main 941a36d66539bb7b0fd59075dab8ba1ae0949e2d; patch d0193d176d4d22b2795d3ea38abd4c29634b76c6 |
| `origin/claude/peaceful-keller-de2832` | `67eec45a50d19975316dfa150b8987fab004b017` | 2026-08-16T01:15:41-04:00 | 3/356 | HOLD open PR #135 | E5 3 unmatched commits; 11/11 branch-touched paths differ |
| `origin/claude/propose-label-writeback` | `f7885524c22e648c9941061c58ebb665dd2623fc` | 2026-08-29T20:55:39-04:00 | 1/34 | SAFE branch cleanup | E4 main 6b4fd64a5a05ffb1b2c3142fad2c60ce976b4ff5; patch 63decc850dad7a92dd6e11a81b0324c3f2ab72e5 |
| `origin/claude/q035-q036-operator-answers` | `832d9ca1e34f3808ecebef3c3ceb7a1910e626e4` | 2026-09-02T15:12:26-04:00 | 1/17 | SAFE branch cleanup | E4 main 02d2eac2564872ce32c3ae2dd76eed5fb945e696; patch e70bd3a27fc248641c18a3ad217b2c5e5bfd9c48 |
| `origin/claude/ram-mascot-fleeced` | `a9b86950dad2975976f383cd1fa8beb242425f02` | 2026-08-23T21:50:34-04:00 | 4/90 | SAFE branch cleanup | E4 main 7ac7869ea69b936e246c7e1f82edf4df023bc6bb; patch 6724d2404f2ed1bbe444a78c3f8c0dcd7969c31e |
| `origin/claude/stoic-mccarthy-e56da9` | `71076178ea3e3e3945b3ca208bb5a799c8d4241c` | 2026-07-03T22:47:20-04:00 | 1/999 | HOLD open PR #91 | E5 1 unmatched commits; 3/3 branch-touched paths differ |
| `origin/claude/team-outlook-experience-27a7a1` | `b3f7d92bd20a68cd7af9eb36da0d463a69326b9a` | 2026-08-20T16:50:20-04:00 | 0/153 | SAFE branch cleanup | E1 tree a2cb8c08ea4f0181c15cdc010fdbb9f6e08b3895 |
| `origin/claude/team-review-analysis-plan-1f91e3` | `34cb825f518370e97679ff45f1d369121dbf943f` | 2026-08-20T00:16:32-04:00 | 1/154 | HOLD unresolved content | E5 1 unmatched commits; 1/1 branch-touched paths differ |
| `origin/claude/trade-model-review-101bf7` | `c211d05ccd66117c8e37b44fad57fa12934bdbd9` | 2026-08-27T23:38:07-04:00 | 2/53 | HOLD open PR #224 | E5 2 unmatched commits; 13/13 branch-touched paths differ |
| `origin/claude/tweet-product-gap-review-266ff1` | `ff340b7aa188ca3a11756adbe92f64d6eb1a74f4` | 2026-08-21T01:12:23-04:00 | 1/126 | HOLD open PR #160 | E5 1 unmatched commits; 1/1 branch-touched paths differ |
| `origin/claude/website-updates-continue-c7942b` | `3c0c0188705ea36dc751a7d572f56c8bfcc90f6d` | 2026-09-02T16:01:08-04:00 | 20/14 | HOLD unresolved content | E3 1 changed paths equal current main |
| `origin/closeout-mock-draft` | `aaa98449d4fdcb4c2c351018f03b1a7613c7dc88` | 2026-08-13T19:11:26-04:00 | 1/402 | SAFE branch cleanup | E4 main 60fccc75d2344910cb5fafb75cfaf3f94e5ea9a2; patch 0b8061421963a86f0f28f3823368dd643cafbcf9 |
| `origin/closeout-wave` | `68e0b4dfc6ca28bc52d0279344f7e805e283f112` | 2026-08-14T00:26:54-04:00 | 1/390 | SAFE branch cleanup | E4 main 2f0fcbb0823499b0e21913e57751d768cc9be929; patch f2564105da3b5c66b32c46f1cf534f36b4908a09 |
| `origin/context-slim-2026-08-08` | `4a381f7eefd535a02018f0b2c7587175c66d9f0f` | 2026-08-08T21:28:44-04:00 | 7/618 | SAFE branch cleanup | E4 main e907c9321ee209d1371028c8cddad8a5c74a8b98; patch d8588abac219c754831e0e8122f5262693db289b |
| `origin/docs-297-302-artifacts` | `7f7524c3822d4feaf3e86223cc204626d3961a2b` | 2026-08-12T00:47:38-04:00 | 3/462 | SAFE branch cleanup | E4 main 62ff8d68221ce126f405e0fefbe9bb90b28cce45; patch de83f059bec6077e534d35a7add7525f8012568d |
| `origin/docs/card-evidence` | `92ea29c071412c54380627768d383b5f5a6a6b06` | 2026-08-19T21:52:26Z | 1/206 | HOLD open PR #140 | E5 1 unmatched commits; 4/4 branch-touched paths differ |
| `origin/docs/feedback-batch-2-prds` | `b59951c984db0318946e11c798b67788ff929f0a` | 2026-06-08T16:06:46-04:00 | 1/1020 | SAFE branch cleanup | E3 8 changed paths equal current main |
| `origin/docs/fit-challenger` | `52414d8696d53305b5b0cabdd1ec6d1778dfd722` | 2026-08-19T23:26:35Z | 1/189 | HOLD unresolved content | E5 1 unmatched commits; 3/5 branch-touched paths differ |
| `origin/docs/landability-c1-measurement` | `fd952b5fdf38eff16eccff7543942372f0c61777` | 2026-08-19T18:47:50-04:00 | 2/206 | HOLD unresolved content | E5 2 unmatched commits; 6/6 branch-touched paths differ |
| `origin/docs/landability-challenger` | `23fee85a2708eb60fcdf9640196d812605b1ed0a` | 2026-08-19T21:16:50Z | 1/206 | HOLD open PR #139 | E5 1 unmatched commits; 5/5 branch-touched paths differ |
| `origin/docs/navdoc-refresh-2026-08-18` | `38a989c88b054ac2d90f443e4866a4faa10f96a3` | 2026-08-18T20:26:27-04:00 | 7/263 | SAFE branch cleanup | E4 main 686c429ddef5a1aab7e9fb9b6969610b476cd1e8; patch 9555daa2dab3cf11fa1dcbed55cdf15d2944b70e |
| `origin/docs/null-dwell-writeback` | `80bb318c0b6e31db48f155edd1eaca4cbb8e3412` | 2026-08-29T22:24:33-04:00 | 1/32 | SAFE branch cleanup | E4 main d5c926fd7d2a3efc2af918560c612bd3967a2102; patch 7329294a93ebeabc6b318a3dae75c0330263113e |
| `origin/docs/ppg-impact` | `644a6676165e4a87b123e9fba0f092f89b0d5c65` | 2026-08-19T22:06:05Z | 1/206 | HOLD open PR #141 | E5 1 unmatched commits; 4/4 branch-touched paths differ |
| `origin/feat/datetime-utcnow-cleanup` | `4a8722959d4c20ab7a324292eff4e3042de0727b` | 2026-06-08T11:48:01-04:00 | 1/1021 | SAFE branch cleanup | E4 main 86448a6f5ffcc67d01086ee798326114881294e3; patch 72aa8b5aeb08d14fdb98037f47ea74caa3cc5b0d |
| `origin/feat/espn-credential-verify` | `2fa1ff24f0ceb143d7b23b79ed5ea874a218a619` | 2026-08-12T00:25:58-04:00 | 0/462 | SAFE branch cleanup | E1 tree 9b7aff83ba0ae5ea5dab828913d080ab42d33374 |
| `origin/feat/fb-07-trios-cleanup` | `fa9979bda197ca601b919f938fec55d2fd9a6314` | 2026-06-08T16:13:20-04:00 | 1/1019 | SAFE branch cleanup | E4 main bb3636ea69c88b515b942f22b4065cc6cc1e220d; patch 62aff5922b0f9142451dee66253bc9a8c71c533d |
| `origin/feat/feedback-admin-list` | `8eabe6c3d111b83fe97fdbe9a20e4bb42356fa4e` | 2026-05-21T09:03:00-04:00 | 1/1049 | SAFE branch cleanup | E4 main 8bdba1245d85b961e228b5a2542cc6914ff9d134; patch 77c66dbd12cb10c0a50da6f967926771261531c8 |
| `origin/feat/feedback-batch-4-polish` | `1d3ffca88de44f41a62e45bf3d3d43437d018785` | 2026-06-19T14:01:41-04:00 | 5/988 | SAFE branch cleanup | E4 main 7a05f4e6294bc347e9d12c03b06774450249c596; patch d05d4a6998525aa62de506391b2597f724c82142 |
| `origin/feat/feedback-liked-trades-waiting` | `8026b7fbc32c3c2a7ddd69aa7585eaf20d94979f` | 2026-05-21T10:34:53-04:00 | 2/1037 | SAFE branch cleanup | E4 main c22e7311d2bc3a575077a69ac444ce24ffb640ab; patch d4c07ff41c954cc736218fe73e616b988e24eb9a |
| `origin/feat/fit-challenger` | `33c649ba97f4f1e5d1e3794f4144673ab709a6a8` | 2026-08-20T00:15:26Z | 2/189 | HOLD open PR #147 | E5 2 unmatched commits; 23/24 branch-touched paths differ |
| `origin/feat/init10-player-view-param` | `2cb2ce792269736d2f41817c54eac77031170334` | 2026-06-08T11:32:59-04:00 | 1/1022 | SAFE branch cleanup | E4 main 2dcac6e3fe317b385b4e518fc71393d4512c6637; patch 4674aaa771ca783698aff8323ee5c48a15cc676b |
| `origin/feat/jon-360-362` | `482b07dd9b86438c20e4593570fd8eeb87d07273` | 2026-08-26T13:36:18-04:00 | 15/63 | SAFE branch cleanup | E4 main 9d983be480f5646b8b9f584220579ecff77c05cd; patch 74f6a6d48376d2db3eab7e1d4b4bae77c273311e |
| `origin/feat/light-tier-flags` | `a362a15ad810b579d73940ffa0a485d1ec55ce86` | 2026-08-20T20:48:18-04:00 | 0/134 | SAFE branch cleanup | E1 tree ec73c5faefcbc62421b44970399a48e3f9742644 |
| `origin/feat/mfl-send-integrated` | `3af201ac7ddd3f18c58fe0f6d7c7fd39c9ccfd4e` | 2026-08-11T16:55:59-04:00 | 0/469 | SAFE branch cleanup | E1 tree 307a9cf736726aaf30bd4b3fa4a15d4f28b0d87b |
| `origin/feat/send-auth-lazy` | `7315d8c62ec30ad47f2a27fdc7d6cbf5ef84aa05` | 2026-08-12T00:06:49-04:00 | 0/463 | SAFE branch cleanup | E1 tree 371965165755be35a66e3aeb86b1677c1958707f |
| `origin/feat/send-in-espn` | `f89d8805c4ebd436705f5d59da1edc4fa9c2c82f` | 2026-08-11T18:05:57-04:00 | 0/465 | SAFE branch cleanup | E1 tree 0a8d54cb088b8c5cd675e40605137b27f3001e41 |
| `origin/feat/sleeper-reachability-probe` | `1f349bd3cbb7742ff3e4301e77e8e7c296eff72d` | 2026-08-12T15:54:59-04:00 | 0/452 | SAFE branch cleanup | E1 tree 0d9d66aef227d70a7baa359ac4fb666611318dcb |
| `origin/feat/team-review-batch-2` | `f56216e5931d336051648b889c23700ce74a1398` | 2026-08-20T18:39:52-04:00 | 0/138 | SAFE branch cleanup | E1 tree a6e17a6812e2e6ae070b7dbf1b4a23940c0427c2 |
| `origin/feat/trade-relevance-p0` | `03dbb2984e3daa89340ae92e88d388d8950f6cc9` | 2026-08-14T22:14:27-04:00 | 9/379 | HOLD unresolved content | E5 7 unmatched commits; 41/41 branch-touched paths differ |
| `origin/feat/wave1-perf` | `c30f4f1d59ca9256c673a7bc44de7b9d785a8328` | 2026-06-07T13:07:06-04:00 | 2/1030 | HOLD unresolved content | E5 1 unmatched commits; 50/55 branch-touched paths differ |
| `origin/feat/wave1-perf-code` | `f248197bbd348fd6790506c51fc6d474c7acb1a5` | 2026-06-07T13:07:43-04:00 | 1/1030 | SAFE branch cleanup | E4 main 464a7a2758c0d11edb41b5aa3701d0e76dfe676b; patch ad2887d4f2f1a356e20ca3e64d7490594cf678f1 |
| `origin/feat/wave2-init07` | `241f2232fc4030e410a902433d69de43fb6ff792` | 2026-06-07T14:01:35-04:00 | 2/1024 | SAFE branch cleanup | E4 main b55dfabd3f7e69a8bd515393603d67dbe997fa7b; patch 98fd5001f038ff8c44e91a375a619ba060649fb4 |
| `origin/feat/wave2-init08-client` | `8c2b5ec37c42e4aded02dfd7bb06bd6fd7fc4575` | 2026-06-07T14:05:22-04:00 | 1/1024 | SAFE branch cleanup | E4 main 38b127f883a761e8ae349708c759d6bb4954a496; patch 7c67c2ebf2ecf719de7ee565ec3ec9b89e2e6073 |
| `origin/feat/wave2-init09-trade-prune` | `bec210780d0049e28c9f91c6f1c3cb4e3688c927` | 2026-06-07T13:38:09-04:00 | 1/1029 | SAFE branch cleanup | E4 main 04cdc058522e3a44c2ef08692a6fa52675e0b646; patch daf9ea48d40808678982f4881ec996909734e50b |
| `origin/feat/wave2-init11a-13` | `040188162b92af41f980d1694d47f69ca0f0ab8c` | 2026-06-07T13:41:16-04:00 | 1/1029 | SAFE branch cleanup | E4 main debfa4f2781b50bfc0372276e007b57f747128b9; patch 9d3c95db25e0065c088b5640315f1ce31173d00e |
| `origin/feat/wave2-init12b` | `20bebe4ceb3065752f954c24d97b259a0bffe158` | 2026-06-07T13:36:34-04:00 | 1/1029 | SAFE branch cleanup | E4 main b2117edd8987d7877e08d44aba5aae6cdaff108c; patch 0ec9f63ea178cdf2051042249c0f572890aedebb |
| `origin/feat/wave2-init14b-db-hygiene` | `cd1248c2b314c536e119c3b130e4b1157bd7f9cf` | 2026-06-07T13:41:59-04:00 | 1/1029 | SAFE branch cleanup | E4 main b8583f63fbbff2649699a9b9eaad6e78e44e995d; patch e3f9d239e7490f2a8f3b8ce692fc621c2958bb04 |
| `origin/feat/wave2-init15-docs` | `a75ba55a6cf00d6f8a9714764e980f913bceb2f5` | 2026-06-07T13:53:37-04:00 | 1/1029 | SAFE branch cleanup | E4 main 7e33cba313fb1badcae53961ae0ed5b61e65b46a; patch 2327057b4762a8b8925ab65e851d9bc17f7c1d58 |
| `origin/feat/window-composite` | `bbc2e4b166925c4417bb5ec559a9241354b1b9fb` | 2026-08-20T21:13:18-04:00 | 0/129 | SAFE branch cleanup | E1 tree c52ce7fe948401be894289311e32cf58882832cd |
| `origin/feedback-289-294` | `660004c13c74e18d3ef2054e87bb925091c97cd1` | 2026-08-10T11:05:23-04:00 | 21/505 | SAFE branch cleanup | E4 main 6c304c7bde576721210366835d2d3d0da445afde; patch c720ed0953aecf7c4c6a91744222824dfde8170d |
| `origin/feedback-integration-v2` | `8cbedf8c6927d0f1413146b2e7a3d4b248ef1174` | 2026-08-11T15:25:38-04:00 | 30/478 | SAFE branch cleanup | E4 main f8acd7159f1a9f63e86309eb19916cbd7be0e5b0; patch 0cfe0947281bfeffbda46b6d657e5ca174cf7aba |
| `origin/fix-easignore-screens` | `978910a4741dc511358931c5de337ec35aea9497` | 2026-08-11T17:01:26-04:00 | 1/477 | SAFE branch cleanup | E3 1 changed paths equal current main |
| `origin/fix/feedback-qc-trio-throttle` | `973ad489cda2b18880fb623eab269bd7bff921e9` | 2026-05-21T09:46:24-04:00 | 1/1048 | SAFE branch cleanup | E4 main bd5a733ea100112b89f4d6de9dd506cce8926634; patch 03fe90fbd464121bb34c7e5dd3e687ec6b8ba783 |
| `origin/fix/feedback-rehydrate-unsynced` | `cacde8af44ab65befae2b3941ccb777d617915a3` | 2026-05-20T20:31:17-04:00 | 1/1050 | SAFE branch cleanup | E4 main e52a8dcd208a9f3847d0c2883865df8857e18826; patch 9463cfeb502dc1baafa3e08aa999b8d17095b989 |
| `origin/fix/feedback-tiers-ux` | `c693581795c7b62138a348d4b60d0c4d9003b247` | 2026-05-21T09:55:39-04:00 | 1/1048 | SAFE branch cleanup | E4 main 807fa66bcd999c7ea2c071296626af603ce7f527; patch 70465a1d7848ff14607d65e9e7d1346cb6b6aed8 |
| `origin/fix/feedback-trade-match-100` | `317e42969a449c3ec34920d9e8540f65eed24114` | 2026-05-21T09:43:49-04:00 | 1/1048 | SAFE branch cleanup | E4 main c8a1f651bb83003f1ca356d4050b6b389aaa9fac; patch a7438531b8bafc971b8df02872d92cfd9af38c9b |
| `origin/fix/feedback-trios-polish` | `cdeb130914e8f72916216764910caaeaf77ab1ab` | 2026-05-21T09:17:23-04:00 | 1/1048 | SAFE branch cleanup | E4 main 4356795eedc3bf69d9c4bf6b9793e7fb6421ab87; patch ae5d521330246e478920e8a32a2a91d5f6d45565 |
| `origin/fix/finder-conditions-and-partners-copy` | `bda0d51844b289dc509f84c71c8a44a15f742fac` | 2026-08-20T20:19:52-04:00 | 0/136 | SAFE branch cleanup | E1 tree 40142c7dfab3412b4c9b5c00e6b57caf19dd9940 |
| `origin/fix/pick-assignment-missing-user-team-clean` | `fc260dea52f39590f4e8b3ac100e83a0d4a5c424` | 2026-08-08T14:23:14-04:00 | 0/630 | SAFE branch cleanup | E1 tree 5c138af3a1ce940ac7811f37958044a854908dda |
| `origin/fix/review-batch-backend-perf` | `8c3a5550b63a53f27af467bbfac280266f41df76` | 2026-05-24T16:00:36-04:00 | 1/1035 | SAFE branch cleanup | E4 main 4f83805d7d50006b2718464ae6e9b9d857787b12; patch cbc8d205c8cf3f3267abc0caf23c1ec01ece2d01 |
| `origin/fix/review-cache-and-mutations` | `9d99ab81efec8e35f3a1f5aa08f3a931b850f325` | 2026-05-24T16:07:22-04:00 | 1/1031 | SAFE branch cleanup | E4 main a1142da0c20d3492d12b6234ae2e082816de249b; patch a90152b45af6818eeb4ed11e4d7b68bee36d43fd |
| `origin/fix/review-flags-and-notifications` | `78b1568fa9275544bb2b32220b169816d208825d` | 2026-05-24T15:58:56-04:00 | 1/1035 | SAFE branch cleanup | E4 main ae029bce29b9bf987db77522c72c0417e6dff4bb; patch 5608f78212a8a3c52dc18121ea25312c302c1ecc |
| `origin/fix/session-init-parallelization` | `5e1a5a879b6cad551b4e0d38f35c51dddd47fef4` | 2026-05-24T16:04:12-04:00 | 1/1032 | SAFE branch cleanup | E4 main b9187716ab9181444cf4d38b6fa0ce2b43e8000a; patch e2ab6a882337e6eb82e50ea82c03b315948236a4 |
| `origin/fix/test-user-logins` | `be9afbd4482fbd432bb2c283bf778d2eafa970a5` | 2026-06-23T00:42:58-04:00 | 1/1000 | SAFE branch cleanup | E4 main 33496d8217e946c517f87a3526db0dfa9dd0a344; patch d204d390c4d2d56856cee8f58186f71e7d037c4f |
| `origin/fix/test-user-logins-tev2` | `34b8d4c3eeaf835efd4bcae94721cf30ae126965` | 2026-06-23T20:56:03-04:00 | 1/987 | SAFE branch cleanup | E4 main 33496d8217e946c517f87a3526db0dfa9dd0a344; patch d204d390c4d2d56856cee8f58186f71e7d037c4f |
| `origin/fix/tiers-drag-worklet-crash` | `ee8c48b5ca0db2d80a9ae0d0f61cb34b709a03f1` | 2026-05-20T19:57:40-04:00 | 1/1052 | SAFE branch cleanup | E4 main f5c8bc3dbe20417e188de771c7aa3329abde4b5a; patch 6c4f3c3343d363669f7ccf44a7d8988039e9a4c6 |
| `origin/fix/tiers-drop-coord-space` | `0a924974a990b96ec7ba98d8a1bfa45ddb430c1d` | 2026-05-22T12:54:54-04:00 | 1/1036 | SAFE branch cleanup | E4 main eedcd2444808213374e62c83b70d7de8eccded3f; patch a1091f12dada9add1c9766c85e072fe813c0d25a |
| `origin/fix/tiers-multiselect` | `ad8471b51f6d92b6c35871c42055061dbd2d32c9` | 2026-06-09T14:04:27-04:00 | 1/1011 | SAFE branch cleanup | E4 main ba647dedf3c5abaec84a45531819257ad9e03146; patch d8429c761ffcafe84064133cda686d9dda59db58 |
| `origin/fix/tiers-rework` | `65bb39ad04369702a133aef44f4b3d80fb6087fd` | 2026-06-09T14:03:52-04:00 | 6/1012 | HOLD unresolved content | E5 5 unmatched commits; 1/1 branch-touched paths differ |
| `origin/infra/render-cron-migration` | `57300ae55db004d9981e4c375972701078459091` | 2026-08-09T22:34:45-04:00 | 1/531 | HOLD open PR #102 | E5 1 unmatched commits; 3/3 branch-touched paths differ |
| `origin/ledger/2026-09-03-fb413-ship` | `1aede146919b9c896944ebd6c46398ab2e64f1d8` | 2026-09-03T00:19:51-04:00 | 2/9 | HOLD unresolved content | E4 main 6ccd6698e97fbac9b37d31e451cf0132060e7b6c; patch 041bce1e2f9bc2c54fb336110e96210538486943 |
| `origin/living-memory-2026-08-10` | `3f073a57543b0cb1b76319d80aca6040fa02bd2c` | 2026-08-10T17:43:41-04:00 | 2/503 | SAFE branch cleanup | E4 main 2e0b2c71988d2679994dfddccd322f4b6dc5d618; patch b43f80f10ca3949edc7a0dd4e9c73b6b1d496dd1 |
| `origin/living-memory-revival` | `f949fec2639dc509d92af217d5c84be52ea76f75` | 2026-08-08T14:17:49-04:00 | 1/632 | SAFE branch cleanup | E4 main f714f52589c32970c193c2a11454790aca3871af; patch 09b6e298f22b4f54839da6954dd15ad98c9b9e1d |
| `origin/main` | `606e512cd87f692eced3b92ccadb4f0192ea3449` | 2026-09-03T14:18:19-04:00 | 0/0 | Protected main | E1 tree ad663e32c2049ad5a46bdfaac38aa245d98b1aa6 |
| `origin/mobile-version-1.12.0` | `c65493dec2b847ef08ad0a7f08bf8217ed90630c` | 2026-08-10T17:21:17-04:00 | 1/504 | SAFE branch cleanup | E4 main 7553874f6eaede94351049b024e980f0a90411b5; patch c12e48ebd5899590b5d8e1c49d2087c59d69a3fd |
| `origin/mock-draft-fix` | `258940ff7a41b8c3fca9f56eb3e7f393a77993ce` | 2026-08-13T18:41:18-04:00 | 19/403 | SAFE branch cleanup | E4 main e71a6541659553fab02c41d35355b6529118a1d3; patch 81f8917ed398703baff71911eeeed6f512701b7e |
| `origin/perf/league-matches-progressive-paint` | `9a3475dfae187d8c7de27170a17de9c651b3e086` | 2026-05-21T09:52:16-04:00 | 1/1048 | SAFE branch cleanup | E4 main 2bf4484c4a4ec29255a708b32f2d63c9ca4b3bea; patch c0569adfe3868e7f88ac58e68f937718c012556d |
| `origin/perf/trade-tier-priority` | `b12488d25c2454b461d4b830d0ed79415d08fed0` | 2026-04-29T20:33:01-04:00 | 1/1069 | SAFE branch cleanup | E4 main 6aa1255d2f79fc003a5e5ac28bd6e7776f003712; patch e627b137e8389425ad0dc711c5da6374425377e6 |
| `origin/perf/trios-fast-load` | `dd8f95b0d2d5d433ac42c3492c549a1a0eab3163` | 2026-05-24T16:00:09-04:00 | 1/1035 | SAFE branch cleanup | E4 main 827add1570ad9434bbb9067d067e33f9bf232eca; patch fdd256de8605246659badd4a6cf8b865a4dba39c |
| `origin/perf/warm-endpoint-and-boot-ping` | `0eca3c4e003a90578a3ed6f0e3a4bc64f478bd05` | 2026-05-21T09:53:09-04:00 | 1/1048 | SAFE branch cleanup | E4 main 71ba9b1edcd577ec64b8c19ba9fd7f953df38fdf; patch 869c6f1f35559416349ad57568dd4aed3c3d92bf |
| `origin/screen-library-2026-08-09` | `dc91a91bd4a88e08f5a9c4e907e698fded436785` | 2026-08-10T20:34:32-04:00 | 18/502 | SAFE branch cleanup | E4 main 6b8270b418f30c84d105d0510292bc280b505137; patch b882904cd2929d7a19cdcc3fe49590e405c4a459 |
| `origin/session-closeout-2026-08-12` | `bc5521f713a05feecbd230027ce183e8330f877f` | 2026-08-12T21:52:30-04:00 | 2/427 | SAFE branch cleanup | E4 main 4a4b6718f8d69c692138a1fdc7e41b5abeb77c89; patch 97bd03f80254d642a85b1be6ff9b2360f6c90246 |
| `origin/teardown-remediation` | `2c10f4cc22bdb8dda49957ac7b6e92c76bee99a8` | 2026-07-25T13:36:55-04:00 | 0/865 | SAFE branch cleanup | E1 tree 60785284b76504f6a0b5cf16faccc2c19fd3c179 |
| `origin/trade-engine-v2` | `ca2b26aad6c695a662895fee8c5108fd291af200` | 2026-07-19T21:26:09-04:00 | 0/893 | SAFE branch cleanup | E1 tree ef9a1f2e42fd55de996cfec8dd437512ae877a0a |
| `origin/wave-integration` | `11e468bb852404c7e26a88b3acea60b05f7b5ca8` | 2026-08-14T00:01:40-04:00 | 29/401 | SAFE branch cleanup | E4 main 7057d8612d208e739b53cec285b3c06e2fda7f41; patch f24e003e955ff3c2dd24098575fae4c66dacf706 |

## Unresolved content by distinct tip

These are holds, not claims that all differing files represent missing work. For each distinct tip, the listed paths are changed by that branch relative to its main merge base and are still non-identical on current main. Matching tip aliases share one examination. The mobile-B5 row remains here as the mechanical E5 result, overridden only by the explicit manual proof above.

<details><summary>agent-12-consolidate-skip-button — a5bbff1f293ba39a38e1ac5c605625ba3a26c086</summary>

Tip subject: Consolidate Trios skip controls to a single Skip button. Main A/B: 1/1079. Unmatched non-merge commits: 1. Merge base: `f93c76af239ea37b36e63f7d3ed4190a38b04eaf`.

Non-identical branch-touched paths:

```text
web/index.html
web/js/app.js
```

</details>

<details><summary>audit/knockout-waterfall-v2, origin/audit/knockout-waterfall-v2 — 290b3ed94d65df782fd9bd1f805b7a343651a531</summary>

Tip subject: docs: knockout waterfall v2 — three arms, the value bar, and the two top-100s. Main A/B: 1/107. Unmatched non-merge commits: 1. Merge base: `941a36d66539bb7b0fd59075dab8ba1ae0949e2d`.

Non-identical branch-touched paths:

```text
docs/reviews/2026-08-22-knockout-waterfall-v2.html
docs/reviews/2026-08-22-knockout-waterfall-v2.md
```

</details>

<details><summary>audit/perf-optimization, origin/audit/perf-optimization — 71ed60b2edf1e88a6e64a99ad6e09ddfb2cddf34</summary>

Tip subject: Perf optimization audit: research, observations, plan, HLD/LLD/requirements. Main A/B: 1/1030. Unmatched non-merge commits: 1. Merge base: `a1142da0c20d3492d12b6234ae2e082816de249b`.

Non-identical branch-touched paths:

```text
docs/code-audit/perf-optimization/README.md
docs/code-audit/perf-optimization/design/hld.md
docs/code-audit/perf-optimization/design/lld.md
docs/code-audit/perf-optimization/design/requirements/README.md
docs/code-audit/perf-optimization/design/requirements/init-01-splash-decouple.md
docs/code-audit/perf-optimization/design/requirements/init-02-coldstart-cache.md
docs/code-audit/perf-optimization/design/requirements/init-03-elo-memoization.md
docs/code-audit/perf-optimization/design/requirements/init-04-nav-prefetch.md
docs/code-audit/perf-optimization/design/requirements/init-05-focus-online-manager.md
docs/code-audit/perf-optimization/design/requirements/init-06-touch-activity-throttle.md
docs/code-audit/perf-optimization/design/requirements/init-07-persisted-cache-keys.md
docs/code-audit/perf-optimization/design/requirements/init-08-session-init-optimistic.md
docs/code-audit/perf-optimization/design/requirements/init-09-trade-gen-prune.md
docs/code-audit/perf-optimization/design/requirements/init-10-web-player-payload.md
docs/code-audit/perf-optimization/design/requirements/init-11-render-memo-virtualization.md
docs/code-audit/perf-optimization/design/requirements/init-12-api-client-resilience.md
docs/code-audit/perf-optimization/design/requirements/init-13-poll-backoff.md
docs/code-audit/perf-optimization/design/requirements/init-14-db-hygiene.md
docs/code-audit/perf-optimization/design/requirements/init-15-compression-docs.md
docs/code-audit/perf-optimization/design/requirements/init-16-league-activity-dedup.md
docs/code-audit/perf-optimization/observations/agent-01-api-client/findings.md
docs/code-audit/perf-optimization/observations/agent-02-data-fetching-cache/findings.md
docs/code-audit/perf-optimization/observations/agent-03-backend-routes/findings.md
docs/code-audit/perf-optimization/observations/agent-04-backend-data-db/findings.md
docs/code-audit/perf-optimization/observations/agent-05-rn-rendering/findings.md
docs/code-audit/perf-optimization/observations/agent-06-network-coldstart/findings.md
docs/code-audit/perf-optimization/observations/agent-06-network-coldstart/measurements.md
docs/code-audit/perf-optimization/plan/optimization-plan.md
docs/code-audit/perf-optimization/plan/priority-matrix.md
docs/code-audit/perf-optimization/research/00-research-methodology.md
docs/code-audit/perf-optimization/research/01-mobile-data-fetching.md
docs/code-audit/perf-optimization/research/02-backend-api-performance.md
docs/code-audit/perf-optimization/research/03-caching-strategies.md
docs/code-audit/perf-optimization/research/04-rn-rendering-list-perf.md
docs/code-audit/perf-optimization/research/05-network-coldstart.md
docs/code-audit/perf-optimization/templates/observation-template.md
docs/code-audit/perf-optimization/templates/recommendation-example.md
docs/code-audit/perf-optimization/templates/scoring-criteria.md
docs/plans/archive/2026/feedback-backend-sync/plan.md
docs/plans/archive/2026/mobile-feature-parity/artifacts/architecture-pre-protocol.md
```

</details>

<details><summary>chalkline-primitives — 794c296551d926df63c97ba352c93f316e8ea263</summary>

Tip subject: chalkline: primitive gap-fill — Button loading/icon, SegmentedTabs, pressable Card, Spinner, Badge icon/mono/dim. Main A/B: 1/981. Unmatched non-merge commits: 1. Merge base: `e0001e60672763f324542146d8b74b02a572ccd3`.

Non-identical branch-touched paths:

```text
docs/design/components.md
mobile/src/components/FeedbackSheet.tsx
mobile/src/components/LeaderboardsSection.tsx
mobile/src/components/LeagueSwitcherSheet.tsx
mobile/src/components/OutlookSheet.tsx
mobile/src/components/PlayerPickerModal.tsx
mobile/src/components/RookieDraftBoardSheet.tsx
mobile/src/components/SuggestionCard.tsx
mobile/src/components/chalkline/Badge.tsx
mobile/src/components/chalkline/Button.tsx
mobile/src/components/chalkline/CLAUDE.md
mobile/src/components/chalkline/Card.tsx
mobile/src/components/chalkline/SegmentedTabs.tsx
mobile/src/components/chalkline/Spinner.tsx
mobile/src/components/chalkline/StyleGuide.tsx
mobile/src/components/chalkline/index.ts
mobile/src/navigation/RootNav.tsx
mobile/src/screens/FeedbackInboxScreen.tsx
mobile/src/screens/LeaguePickerScreen.tsx
mobile/src/screens/LeagueScreen.tsx
mobile/src/screens/ManualRanksScreen.tsx
mobile/src/screens/MatchesScreen.tsx
mobile/src/screens/PortfolioScreen.tsx
mobile/src/screens/ProfileScreen.tsx
mobile/src/screens/RankScreen.tsx
mobile/src/screens/SettingsScreen.tsx
mobile/src/screens/SignInScreen.tsx
mobile/src/screens/TiersScreen.tsx
mobile/src/screens/TradesScreen.tsx
mobile/src/screens/TrendsScreen.tsx
```

</details>

<details><summary>claude/ci-check-js-doc-fix — b67d7b3a8e59c6d7b7d959151566cb7c14a1d0e4</summary>

Tip subject: docs: the check-*.js suites DO gate CI — correct the operating contract (Q-024). Main A/B: 1/55. Unmatched non-merge commits: 1. Merge base: `30070f3692cc08cd5dde8c96da2877642f4f73ca`.

Non-identical branch-touched paths:

```text
.github/CLAUDE.md
CLAUDE.md
docs/templates/feature-scope.md
living-memory/CHANGELOG.md
living-memory/NEXT.md
living-memory/OPEN_QUESTIONS.md
```

</details>

<details><summary>claude/ledger-correction-partner-summary, origin/claude/ledger-correction-partner-summary — ba8e84d17ffeb63b6ec0d3e7f2f707bc9ba912b8</summary>

Tip subject: recovery: correct the write-back branch's deletion sha (aee848a5, not 61169c87). Main A/B: 1/53. Unmatched non-merge commits: 1. Merge base: `69dc0cae7db1cd41a522dfb7d33f280038d318c2`.

Non-identical branch-touched paths:

```text
docs/recovery/2026-08-27-partner-summary-branches.md
```

</details>

<details><summary>claude/loving-shtern-12e4b1 — c7ee5b027302fac3f2a3f70253a5055017696385</summary>

Tip subject: ship record: compressed-board fixes merged (PR #122, main 19d4174), deploy + post-deploy deck read verified. Main A/B: 4/377. Unmatched non-merge commits: 2. Merge base: `1bf064572ee79db11c7ee7ad84be6e4de6efb5b2`.

Non-identical branch-touched paths:

```text
backend/feature_flags.py
backend/tests/fixtures/flags/onboarding-v2.json
backend/tests/fixtures/flags/profiles-on.json
backend/tests/fixtures/flags/release.json
backend/trade_optimizer.py
backend/trade_service.py
config/features.json
docs/config-reference.md
docs/glossary.md
living-memory/CHANGELOG.md
living-memory/DECISIONS.md
living-memory/GOTCHAS.md
living-memory/HANDOFF.md
living-memory/NEXT.md
living-memory/OPEN_QUESTIONS.md
living-memory/TEST_LEDGER.md
```

</details>

<details><summary>claude/manual-calculator-e2e-review-39a467 — a12c8b7bef40e04608abfbf44f0fb7096cbd6b56</summary>

Tip subject: living-memory + docs: #384 SHIPPED — PR #172, flags LIT, app 1.16.0. Main A/B: 21/106. Unmatched non-merge commits: 20. Merge base: `613a34c3f55d4bd060c5b5ddf6a59a6f74e52bba`.

Non-identical branch-touched paths:

```text
backend/analytics_queries.py
backend/analytics_taxonomy.py
backend/database.py
backend/feature_flags.py
backend/server.py
backend/tests/fixtures/flags/onboarding-v2.json
backend/tests/fixtures/flags/profiles-on.json
backend/tests/fixtures/flags/release-300.json
backend/tests/fixtures/flags/release-espn-send-off.json
backend/tests/fixtures/flags/release.json
backend/tests/test_bakeoff_arm_a_golden.py
backend/tests/test_calc_trade_queue.py
backend/tests/test_fair_packages.py
backend/trade_service.py
config/features.json
docs/api-reference.md
docs/architecture.md
docs/config-reference.md
docs/cross-client-invariants.md
docs/feedback/items/384-calc-finder-merge/status.md
docs/feedback/items/384-calc-finder-merge/testflight-checklist.md
docs/feedback/items/INDEX.md
docs/glossary.md
docs/plans/README.md
docs/plans/three-model-bakeoff/scope-phase2.md
living-memory/CHANGELOG.md
living-memory/DECISIONS.md
living-memory/GOTCHAS.md
living-memory/HANDOFF.md
living-memory/LLD.md
living-memory/OPEN_QUESTIONS.md
living-memory/TEST_LEDGER.md
mobile/CLAUDE.md
mobile/app.json
mobile/ios/DTFDynastyTradeFinder.xcodeproj/project.pbxproj
mobile/ios/DTFDynastyTradeFinder/Info.plist
mobile/package.json
mobile/src/api/CLAUDE.md
mobile/src/api/trades.ts
mobile/src/components/CLAUDE.md
mobile/src/components/InLeagueCalculator.tsx
mobile/src/components/TradeCard.tsx
mobile/src/components/TradeSide.tsx
mobile/src/components/analystScript.ts
mobile/src/screens/CLAUDE.md
mobile/src/screens/TradeCalculatorScreen.tsx
mobile/src/screens/TradesScreen.tsx
mobile/src/state/CLAUDE.md
mobile/src/state/useGuide.ts
mobile/src/utils/CLAUDE.md
mobile/src/utils/calcTour.ts
mobile/tests/README.md
mobile/tests/check-calc-merged-behavior.js
mobile/tests/check-calc-merged-layout.js
mobile/tests/check-calc-tour.js
mobile/tests/check-guide-script.js
mobile/tests/check-guide-spotlight-tracking.js
mobile/tests/check-offer-prefill-330.js
```

</details>

<details><summary>claude/modest-cerf-12ce88 — 41c50a0997b066a027d34efa5786df46e46d89bf</summary>

Tip subject: mobile-testing: build the tracked testID lint (LLD §2.6). Main A/B: 1/619. Unmatched non-merge commits: 1. Merge base: `6cb2a542d2cd733d970404749455a5d7c1d17c90`.

Non-identical branch-touched paths:

```text
.gitignore
docs/plans/archive/2026/espn-connect-webview/scope.md
docs/plans/archive/2026/mobile-testing/lld.md
docs/plans/archive/2026/mobile-testing/test-cases.md
docs/runbook.md
living-memory/TEST_LEDGER.md
mobile/scripts/testid-lint.sh
```

</details>

<details><summary>claude/new-user-feedback-06dabd, origin/claude/new-user-feedback-06dabd — cd1d243bfa59d4291729730166b5a16d167dfde3</summary>

Tip subject: D-178 QA round 1: declined-offer parity (B-1), excluded_count contract (C-4), 60s cache hole (B-5), honest empty copy (B-2/B-3/B-6), flag-coupling runbook + log. Main A/B: 14/5. Unmatched non-merge commits: 11. Merge base: `a65bb7711ed83e14ed85f8a2274fb91e7e984ed7`.

Non-identical branch-touched paths:

```text
.claude/skills/feedback/lessons.md
backend/server.py
backend/tests/test_asset_ideas.py
backend/tests/test_fair_packages.py
backend/trade_service.py
docs/api-reference.md
docs/config-reference.md
docs/feedback/items/417-pushed-deck-second-search/build-notes.md
docs/feedback/items/417-pushed-deck-second-search/investigation.md
docs/feedback/items/417-pushed-deck-second-search/prd.md
docs/feedback/items/417-pushed-deck-second-search/qa-A.md
docs/feedback/items/417-pushed-deck-second-search/qa-B.md
docs/feedback/items/417-pushed-deck-second-search/scope.md
docs/feedback/items/417-pushed-deck-second-search/status.md
docs/feedback/items/418-shop-send-dismiss/backend-prd.md
docs/feedback/items/418-shop-send-dismiss/backend-qa-A.md
docs/feedback/items/418-shop-send-dismiss/backend-qa-B.md
docs/feedback/items/418-shop-send-dismiss/backend-scope.md
docs/feedback/items/418-shop-send-dismiss/build-notes.md
docs/feedback/items/418-shop-send-dismiss/followup-backend-like-exclusion.md
docs/feedback/items/418-shop-send-dismiss/plan.md
docs/feedback/items/418-shop-send-dismiss/prd.md
docs/feedback/items/418-shop-send-dismiss/qa-A.md
docs/feedback/items/418-shop-send-dismiss/qa-B.md
docs/feedback/items/418-shop-send-dismiss/reconciliation-log.md
docs/feedback/items/418-shop-send-dismiss/scope.md
docs/feedback/items/418-shop-send-dismiss/status.md
docs/feedback/items/INDEX.md
docs/runbook.md
living-memory/DECISIONS.md
living-memory/NEXT.md
living-memory/TEST_LEDGER.md
mobile/app.json
mobile/ios/DTFDynastyTradeFinder.xcodeproj/project.pbxproj
mobile/ios/DTFDynastyTradeFinder/Info.plist
mobile/src/api/trades.ts
mobile/src/components/AssetIdeasPanel.tsx
mobile/src/components/ShopOffersBody.tsx
mobile/src/screens/TradesScreen.tsx
mobile/tests/check-analytics-297-302.js
mobile/tests/check-canvas-results.js
mobile/tests/check-inline-home.js
mobile/tests/check-offer-prefill-330.js
mobile/tests/check-results-push.js
mobile/tests/check-shop-deck.js
```

</details>

<details><summary>claude/new-user-feedback-d4c47d — af8074bd5654d26fe6d9e33ae6f77dd31bf4ca26</summary>

Tip subject: #384: round-2 rulings, and the two things ruling 3 breaks. Main A/B: 4/108. Unmatched non-merge commits: 4. Merge base: `9e1a8be1a6612ef2e6b6be99ef96bf46b2d33f27`.

Non-identical branch-touched paths:

```text
backend/server.py
docs/api-reference.md
docs/cross-client-invariants.md
docs/data-dictionary.md
docs/feedback/items/384-calc-finder-merge/plan.md
docs/feedback/items/384-calc-finder-merge/status.md
docs/feedback/items/INDEX.md
docs/plans/README.md
living-memory/CHANGELOG.md
living-memory/DECISIONS.md
living-memory/GOTCHAS.md
living-memory/TEST_LEDGER.md
mobile/package.json
```

</details>

<details><summary>claude/peaceful-keller-de2832, origin/claude/peaceful-keller-de2832 — 67eec45a50d19975316dfa150b8987fab004b017</summary>

Tip subject: living-memory: HANDOFF — PR #135 green, awaiting operator merge. Main A/B: 3/356. Unmatched non-merge commits: 3. Merge base: `2c67ea021398e1f7cfbb740a8046703a77147944`.

Non-identical branch-touched paths:

```text
docs/feedback/items/189-always-offer-fallback/scope-deck-disclosure.md
docs/glossary.md
living-memory/CHANGELOG.md
living-memory/HANDOFF.md
living-memory/TEST_LEDGER.md
mobile/package.json
mobile/src/api/trades.ts
mobile/src/components/CLAUDE.md
mobile/src/components/TradeCard.tsx
mobile/src/shared/types.ts
mobile/tests/check-relaxed-disclosure.js
```

</details>

<details><summary>claude/ram-mascot-brief-exec-6bb3b7 — 432f8075d570a0a2c975a06d61e03555c06a8c87</summary>

Tip subject: wip: ram mascot Parts 1-2 (pre-reconcile snapshot). Main A/B: 19/107. Unmatched non-merge commits: 19. Merge base: `941a36d66539bb7b0fd59075dab8ba1ae0949e2d`.

Non-identical branch-touched paths:

```text
backend/analytics_queries.py
backend/analytics_taxonomy.py
backend/database.py
backend/feature_flags.py
backend/server.py
backend/tests/fixtures/flags/onboarding-v2.json
backend/tests/fixtures/flags/profiles-on.json
backend/tests/fixtures/flags/release-300.json
backend/tests/fixtures/flags/release-espn-send-off.json
backend/tests/fixtures/flags/release.json
backend/tests/test_analytics_taxonomy_384.py
backend/tests/test_calc_trade_queue.py
config/features.json
context.md
docs/api-reference.md
docs/architecture.md
docs/business/analytics/2026-08-22-384-calc-finder-addendum.md
docs/config-reference.md
docs/cross-client-invariants.md
docs/design/brand.md
docs/feedback/items/384-calc-finder-merge/scope.md
docs/feedback/items/384-calc-finder-merge/status.md
docs/feedback/items/384-calc-finder-merge/testflight-checklist.md
docs/feedback/items/INDEX.md
docs/glossary.md
docs/plans/README.md
living-memory/BRAND.md
living-memory/CHANGELOG.md
living-memory/DECISIONS.md
living-memory/GLOSSARY.md
living-memory/GOTCHAS.md
living-memory/HANDOFF.md
living-memory/LLD.md
living-memory/OPEN_QUESTIONS.md
living-memory/TEST_LEDGER.md
mobile/CLAUDE.md
mobile/assets/CLAUDE.md
mobile/package.json
mobile/src/api/CLAUDE.md
mobile/src/api/trades.ts
mobile/src/components/CLAUDE.md
mobile/src/components/InLeagueCalculator.tsx
mobile/src/components/TradeCard.tsx
mobile/src/components/TradeSide.tsx
mobile/src/components/analystScript.ts
mobile/src/screens/CLAUDE.md
mobile/src/screens/TradeCalculatorScreen.tsx
mobile/src/screens/TradesScreen.tsx
mobile/src/state/CLAUDE.md
mobile/src/state/useFinderTargets.ts
mobile/src/state/useGuide.ts
mobile/src/utils/CLAUDE.md
mobile/src/utils/calcTour.ts
mobile/tests/README.md
mobile/tests/check-analytics-297-302.js
mobile/tests/check-calc-merged-behavior.js
mobile/tests/check-calc-merged-layout.js
mobile/tests/check-calc-tour.js
mobile/tests/check-guide-script.js
mobile/tests/check-offer-prefill-330.js
mockups/CLAUDE.md
mockups/avatar-lab/ram-decisions.html
mockups/avatar-lab/ram-poses.html
mockups/avatar-lab/ram-versions.html
```

</details>

<details><summary>claude/sad-benz-9922d6 — b7015531815d4513b78e0e0ba714e2bafa669553</summary>

Tip subject: lld: mark testID registry ids that don't resolve in mobile/src as planned-not-built. Main A/B: 1/499. Unmatched non-merge commits: 1. Merge base: `ab9368f81aa580a007cc49c91240754206d3e1ec`.

Non-identical branch-touched paths:

```text
docs/plans/archive/2026/mobile-testing/lld.md
```

</details>

<details><summary>claude/team-review-analysis-plan-1f91e3 — 5aff1ce9ab6990900fdcb20ca2e80d6532e4a044</summary>

Tip subject: Merge remote-tracking branch 'origin/main' into claude/team-review-analysis-plan-1f91e3. Main A/B: 2/107. Unmatched non-merge commits: 1. Merge base: `941a36d66539bb7b0fd59075dab8ba1ae0949e2d`.

Non-identical branch-touched paths:

```text
living-memory/CHANGELOG.md
```

</details>

<details><summary>claude/trade-model-review-101bf7, origin/claude/trade-model-review-101bf7 — c211d05ccd66117c8e37b44fad57fa12934bdbd9</summary>

Tip subject: outlook/age plan: dual-agent execution plan + grounding + code map. Main A/B: 2/53. Unmatched non-merge commits: 2. Merge base: `69dc0cae7db1cd41a522dfb7d33f280038d318c2`.

Non-identical branch-touched paths:

```text
docs/plans/trade-model-review/champion-recommendation.md
docs/plans/trade-model-review/current-state.md
docs/plans/trade-model-review/data-readout-2026-08-27.md
docs/plans/trade-model-review/hypothesis-results.md
docs/plans/trade-model-review/outlook-age-code-map.md
docs/plans/trade-model-review/outlook-age-grounding.md
docs/plans/trade-model-review/outlook-age-plan.md
docs/plans/trade-model-review/plan-2026-08-27.md
living-memory/CHANGELOG.md
living-memory/HANDOFF.md
living-memory/NEXT.md
living-memory/OPEN_QUESTIONS.md
living-memory/TEST_LEDGER.md
```

</details>

<details><summary>claude/tweet-product-gap-review-266ff1, origin/claude/tweet-product-gap-review-266ff1 — ff340b7aa188ca3a11756adbe92f64d6eb1a74f4</summary>

Tip subject: NEXT: queue the four production-visibility gaps (operator, 2026-08-21). Main A/B: 1/126. Unmatched non-merge commits: 1. Merge base: `451d2ebd714033a3b1f6bba3fc1b939f9d086efb`.

Non-identical branch-touched paths:

```text
living-memory/NEXT.md
```

</details>

<details><summary>design/device-side-platform-auth — 10f6592613c6157bf564bdbb3dc83d3242c84cb9</summary>

Tip subject: design: device-side platform auth HLD + ADR-011 (design only, nothing built). Main A/B: 1/453. Unmatched non-merge commits: 1. Merge base: `4c0213b2a52f20e9aea7817aacffb703da39a9e7`.

Non-identical branch-touched paths:

```text
docs/adr/README.md
docs/adr/adr-011-device-side-platform-auth.md
docs/plans/device-side-platform-auth-hld-2026-08-12.md
```

</details>

<details><summary>docs/espn-api-reference — ffec7f209687775f8ca2f13d4cd0e86866f0dc3a</summary>

Tip subject: docs(espn): extend integration reference to cover the write surface. Main A/B: 1/465. Unmatched non-merge commits: 1. Merge base: `f89d8805c4ebd436705f5d59da1edc4fa9c2c82f`.

Non-identical branch-touched paths:

```text
docs/integrations/README.md
docs/integrations/espn.md
```

</details>

<details><summary>docs/landability-c1-measurement, origin/docs/landability-c1-measurement — fd952b5fdf38eff16eccff7543942372f0c61777</summary>

Tip subject: docs: C1 measurement note — both-ways doubles the deck, not collapses it. Main A/B: 2/206. Unmatched non-merge commits: 2. Merge base: `50e0451d4db14f91535479c84ae9a42113037900`.

Non-identical branch-touched paths:

```text
docs/plans/README.md
docs/plans/landability-challenger/PRD.md
docs/plans/landability-challenger/README.md
docs/plans/landability-challenger/measurement.md
docs/plans/landability-challenger/scope.md
docs/plans/three-model-bakeoff/PLAN.md
```

</details>

<details><summary>feat/calc-finder-merge — 7399e182ca7607f35403a0215846d40dca7a1d38</summary>

Tip subject: #384: evidence trail for W0-W4 — checklist, D-150, CHANGELOG, TEST_LEDGER. Main A/B: 8/107. Unmatched non-merge commits: 8. Merge base: `941a36d66539bb7b0fd59075dab8ba1ae0949e2d`.

Non-identical branch-touched paths:

```text
backend/feature_flags.py
backend/tests/fixtures/flags/onboarding-v2.json
backend/tests/fixtures/flags/profiles-on.json
backend/tests/fixtures/flags/release-300.json
backend/tests/fixtures/flags/release-espn-send-off.json
backend/tests/fixtures/flags/release.json
config/features.json
docs/config-reference.md
docs/feedback/items/384-calc-finder-merge/plan.md
docs/feedback/items/384-calc-finder-merge/status.md
docs/feedback/items/384-calc-finder-merge/testflight-checklist.md
docs/feedback/items/INDEX.md
living-memory/CHANGELOG.md
living-memory/DECISIONS.md
living-memory/TEST_LEDGER.md
mobile/CLAUDE.md
mobile/package.json
mobile/src/api/CLAUDE.md
mobile/src/components/InLeagueCalculator.tsx
mobile/src/components/TradeCard.tsx
mobile/src/components/TradeSide.tsx
mobile/src/components/analystScript.ts
mobile/src/screens/TradeCalculatorScreen.tsx
mobile/src/screens/TradesScreen.tsx
mobile/src/utils/CLAUDE.md
mobile/src/utils/calcTour.ts
mobile/tests/check-calc-merged-behavior.js
mobile/tests/check-calc-merged-layout.js
mobile/tests/check-calc-tour.js
mobile/tests/check-decline-reasons.js
mobile/tests/check-demo-calc-removed.js
mobile/tests/check-guide-script.js
mobile/tests/check-tour-suppression.js
```

</details>

<details><summary>feat/exact-slot-pick-pricing — 82f05c4629bbf1b0cf994c1ca69ce47f648a28d1</summary>

Tip subject: recovery ledger: throwaway baseline worktree removed (detached at origin/main 17029ac). Main A/B: 2/158. Unmatched non-merge commits: 2. Merge base: `fe191f6605d23a2a5252d8c445769ba20a321864`.

Non-identical branch-touched paths:

```text
backend/database.py
backend/pick_values.py
backend/server.py
backend/tests/test_bakeoff_arm_a_golden.py
backend/tests/test_exact_slot_pricing.py
backend/tests/test_slot_values.py
backend/trade_service.py
config/features.json
docs/api-reference.md
docs/config-reference.md
docs/data-dictionary.md
docs/plans/exact-slot-pricing/scope.md
docs/plans/three-model-bakeoff/scope-phase2.md
docs/recovery/2026-08-19-exact-slot-pricing-baseline-worktree.md
living-memory/CHANGELOG.md
living-memory/DECISIONS.md
living-memory/LLD.md
living-memory/NEXT.md
living-memory/OPEN_QUESTIONS.md
living-memory/TEST_LEDGER.md
```

</details>

<details><summary>feat/exclude-recently-traded — 22cd5853b3edef2fcd7bc394268b1fa726d55e52</summary>

Tip subject: feat(trade): never suggest re-acquiring a player traded away in 30d (D-079). Main A/B: 1/246. Unmatched non-merge commits: 1. Merge base: `02e27dda7446dcf5289c2168776694d86d73395a`.

Non-identical branch-touched paths:

```text
backend/database.py
backend/recent_trade_filter.py
backend/server.py
backend/tests/test_bakeoff_arm_a_golden.py
backend/tests/test_recent_trade_filter.py
backend/trade_service.py
docs/architecture.md
docs/config-reference.md
docs/glossary.md
docs/plans/recent-trade-exclusion/code-walk.md
docs/plans/recent-trade-exclusion/scope.md
docs/plans/three-model-bakeoff/scope-phase2.md
living-memory/CHANGELOG.md
living-memory/DECISIONS.md
living-memory/TEST_LEDGER.md
```

</details>

<details><summary>feat/fb395-lineup-impact-backend — 3e75494e47788c55100517de0238c08047c17f4e</summary>

Tip subject: #395/#396 backend docs: api-reference row + Group C status build report. Main A/B: 6/81. Unmatched non-merge commits: 6. Merge base: `ff153a0f7eab8bbf257c8bc8c2779a3d690dec2e`.

Non-identical branch-touched paths:

```text
.claude/skills/feedback/lessons.md
backend/server.py
backend/tests/test_trade_evaluate.py
docs/api-reference.md
docs/feedback/items/346-quickset-tier-drop/plan.md
docs/feedback/items/346-quickset-tier-drop/prd.md
docs/feedback/items/346-quickset-tier-drop/status.md
docs/feedback/items/376-finder-filters-regression/prd.md
docs/feedback/items/376-finder-filters-regression/status.md
docs/feedback/items/386-analyst-playoff-odds/status.md
docs/feedback/items/395-lineup-impact-superflex/status.md
docs/feedback/items/397-swipe-tour-placement/status.md
docs/feedback/items/INDEX.md
```

</details>

<details><summary>feat/fb4-tiers-polish — b49e5b9eae329150783f248f824849019fc13571</summary>

Tip subject: FB4-61/62/63: Tiers tile stats + toggle, quick tier-move, sticky tier header. Main A/B: 1/988. Unmatched non-merge commits: 1. Merge base: `a39e1e13f866ee257dec39d4f99d24d124fb877d`.

Non-identical branch-touched paths:

```text
mobile/src/components/TierStickyHeader.tsx
mobile/src/components/TierTargetChips.tsx
mobile/src/components/TileStats.tsx
mobile/src/screens/TiersScreen.tsx
```

</details>

<details><summary>feat/fb4-trades-gate — ba1c730ef1c25f64e6393cc93b0c55fa3170fc7d</summary>

Tip subject: FB4-59: TradesHome single-format gate error with copy/setup actions. Main A/B: 1/988. Unmatched non-merge commits: 1. Merge base: `a39e1e13f866ee257dec39d4f99d24d124fb877d`.

Non-identical branch-touched paths:

```text
mobile/src/components/FormatGate.tsx
mobile/src/screens/TradesScreen.tsx
```

</details>

<details><summary>feat/fb417-pushed-deck-research — 6cd5c4902ffa49e85f748969d58a5b48f82aafcc</summary>

Tip subject: fix(mobile): FB-417 — the pushed anchored deck cannot start a second, unanchored search. Main A/B: 4/10. Unmatched non-merge commits: 4. Merge base: `c7e756662f82fe6d48a0e03e6f73240b2d34fbd5`.

Non-identical branch-touched paths:

```text
.claude/skills/feedback/lessons.md
docs/feedback/items/417-pushed-deck-second-search/build-notes.md
docs/feedback/items/417-pushed-deck-second-search/investigation.md
docs/feedback/items/417-pushed-deck-second-search/prd.md
docs/feedback/items/417-pushed-deck-second-search/scope.md
docs/feedback/items/417-pushed-deck-second-search/status.md
docs/feedback/items/418-shop-send-dismiss/build-notes.md
docs/feedback/items/418-shop-send-dismiss/plan.md
docs/feedback/items/418-shop-send-dismiss/prd.md
docs/feedback/items/418-shop-send-dismiss/reconciliation-log.md
docs/feedback/items/418-shop-send-dismiss/scope.md
docs/feedback/items/418-shop-send-dismiss/status.md
docs/feedback/items/INDEX.md
mobile/src/components/ShopOffersBody.tsx
mobile/src/screens/TradesScreen.tsx
mobile/tests/check-analytics-297-302.js
mobile/tests/check-canvas-results.js
mobile/tests/check-inline-home.js
mobile/tests/check-offer-prefill-330.js
mobile/tests/check-results-push.js
mobile/tests/check-shop-deck.js
```

</details>

<details><summary>feat/fb418-backend-like-exclusion — 77a4e33b1c08acda487892d77a9e204290ccd3ec</summary>

Tip subject: D-178: a sent offer is a LIKE on the idea routes (#418 backend follow-up). Main A/B: 13/5. Unmatched non-merge commits: 10. Merge base: `a65bb7711ed83e14ed85f8a2274fb91e7e984ed7`.

Non-identical branch-touched paths:

```text
.claude/skills/feedback/lessons.md
backend/server.py
backend/tests/test_asset_ideas.py
backend/tests/test_fair_packages.py
backend/trade_service.py
docs/api-reference.md
docs/config-reference.md
docs/feedback/items/417-pushed-deck-second-search/build-notes.md
docs/feedback/items/417-pushed-deck-second-search/investigation.md
docs/feedback/items/417-pushed-deck-second-search/prd.md
docs/feedback/items/417-pushed-deck-second-search/qa-A.md
docs/feedback/items/417-pushed-deck-second-search/qa-B.md
docs/feedback/items/417-pushed-deck-second-search/scope.md
docs/feedback/items/417-pushed-deck-second-search/status.md
docs/feedback/items/418-shop-send-dismiss/backend-prd.md
docs/feedback/items/418-shop-send-dismiss/backend-scope.md
docs/feedback/items/418-shop-send-dismiss/build-notes.md
docs/feedback/items/418-shop-send-dismiss/followup-backend-like-exclusion.md
docs/feedback/items/418-shop-send-dismiss/plan.md
docs/feedback/items/418-shop-send-dismiss/prd.md
docs/feedback/items/418-shop-send-dismiss/qa-A.md
docs/feedback/items/418-shop-send-dismiss/qa-B.md
docs/feedback/items/418-shop-send-dismiss/reconciliation-log.md
docs/feedback/items/418-shop-send-dismiss/scope.md
docs/feedback/items/418-shop-send-dismiss/status.md
docs/feedback/items/INDEX.md
living-memory/DECISIONS.md
living-memory/NEXT.md
living-memory/TEST_LEDGER.md
mobile/app.json
mobile/ios/DTFDynastyTradeFinder.xcodeproj/project.pbxproj
mobile/ios/DTFDynastyTradeFinder/Info.plist
mobile/src/components/ShopOffersBody.tsx
mobile/src/screens/TradesScreen.tsx
mobile/tests/check-analytics-297-302.js
mobile/tests/check-canvas-results.js
mobile/tests/check-inline-home.js
mobile/tests/check-offer-prefill-330.js
mobile/tests/check-results-push.js
mobile/tests/check-shop-deck.js
```

</details>

<details><summary>feat/finder-config-and-draft-order — e174b2965864fbd0ce284a18203e2b96bd553eec</summary>

Tip subject: trade.finder_config_consolidated: fold Specific-Team/Player finder modes into one Trade Configuration card. Main A/B: 2/629. Unmatched non-merge commits: 2. Merge base: `cb6aacbb3f4f0d55734df7c4928cd73e3a0ef53c`.

Non-identical branch-touched paths:

```text
backend/feature_flags.py
backend/server.py
backend/tests/fixtures/flags/release.json
backend/tests/test_finder_config_consolidated.py
backend/trade_service.py
config/features.json
docs/api-reference.md
docs/config-reference.md
mobile/src/api/trades.ts
mobile/src/screens/PickAssignmentScreen.tsx
mobile/src/screens/TradesScreen.tsx
```

</details>

<details><summary>feat/gap-sweetener-arm-c — 9e4469fe5425138befb4cbdeddba14a45acb8b90</summary>

Tip subject: living-memory: handoff for the stacked arm-C sweetener branch. Main A/B: 8/124. Unmatched non-merge commits: 8. Merge base: `eb9c1dee7029a301d4bda535f12b380b8f80ddbc`.

Non-identical branch-touched paths:

```text
backend/bakeoff_profiles.py
backend/database.py
backend/server.py
backend/tests/test_asset_ideas.py
backend/tests/test_bakeoff_arm_a_golden.py
backend/tests/test_bakeoff_serving.py
backend/tests/test_gap_sweetener.py
backend/trade_gen_v2.py
backend/trade_optimizer.py
backend/trade_service.py
docs/config-reference.md
docs/plans/package-benchmark-sweetener/scope.md
docs/plans/three-model-bakeoff/scope-phase2.md
living-memory/GOTCHAS.md
living-memory/HANDOFF.md
living-memory/LLD.md
living-memory/TEST_LEDGER.md
```

</details>

<details><summary>feat/jon-357-360-362 — 43c0b4b5416502ae826ad0fdd854967a4ebb8d4e</summary>

Tip subject: feat(#360,#362): backend — avoiding positions + standing offers. Main A/B: 4/206. Unmatched non-merge commits: 4. Merge base: `50e0451d4db14f91535479c84ae9a42113037900`.

Non-identical branch-touched paths:

```text
backend/analytics_queries.py
backend/analytics_taxonomy.py
backend/database.py
backend/feature_flags.py
backend/server.py
backend/tests/fixtures/flags/onboarding-v2.json
backend/tests/fixtures/flags/profiles-on.json
backend/tests/fixtures/flags/release.json
backend/tests/test_avoid_positions.py
backend/tests/test_standing_offers.py
backend/trade_optimizer.py
backend/trade_service.py
config/features.json
docs/api-reference.md
docs/config-reference.md
docs/cross-client-invariants.md
docs/data-dictionary.md
docs/feedback/items/360-avoiding-positions/code-walk.md
docs/feedback/items/360-avoiding-positions/hld-delta.md
docs/feedback/items/360-avoiding-positions/lld-delta.md
docs/feedback/items/360-avoiding-positions/plan.md
docs/feedback/items/360-avoiding-positions/prd.md
docs/feedback/items/360-avoiding-positions/scope.md
docs/feedback/items/362-standing-offer/hld-delta.md
docs/feedback/items/362-standing-offer/plan.md
docs/feedback/items/362-standing-offer/prd.md
docs/feedback/items/362-standing-offer/scope.md
docs/glossary.md
mockups/CLAUDE.md
mockups/standing-offer-362/README.md
mockups/standing-offer-362/index.html
```

</details>

<details><summary>feat/manual-ranking-up-down-arrows — 01d38b7aa6df2d4dd48efae55f33c279c0098b9f</summary>

Tip subject: Add up/down arrow controls to Manual Rankings rows. Main A/B: 1/1079. Unmatched non-merge commits: 1. Merge base: `f93c76af239ea37b36e63f7d3ed4190a38b04eaf`.

Non-identical branch-touched paths:

```text
web/css/styles.css
web/index.html
web/js/app.js
```

</details>

<details><summary>feat/mobile-b1-manual-rankings-and-copy-tiers — 5d5b4966090839a47bea07fb279590f09cb2aa28</summary>

Tip subject: Mobile B1: Manual Rankings screen + Tier copy-from-format. Main A/B: 1/1056. Unmatched non-merge commits: 1. Merge base: `87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5`.

Non-identical branch-touched paths:

```text
mobile/package-lock.json
mobile/package.json
mobile/src/api/league.ts
mobile/src/api/rankings.ts
mobile/src/navigation/TabNav.tsx
mobile/src/screens/ManualRanksScreen.tsx
mobile/src/screens/TiersScreen.tsx
```

</details>

<details><summary>feat/mobile-b2-trends-screen — ab97ecb75df1779d49ea4da7f08a016df13735ae</summary>

Tip subject: Mobile B2: Trends screen — risers, fallers, and consensus gap. Main A/B: 1/1056. Unmatched non-merge commits: 1. Merge base: `87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5`.

Non-identical branch-touched paths:

```text
mobile/src/api/rankings.ts
mobile/src/components/TrendBar.tsx
mobile/src/navigation/TabNav.tsx
mobile/src/screens/TrendsScreen.tsx
mobile/src/shared/types.ts
```

</details>

<details><summary>feat/mobile-b3-portfolio-and-multi-league — 91b2924077c7ef3bc528076d8540211258a23595</summary>

Tip subject: Mobile B3: Portfolio screen + multi-league switcher. Main A/B: 1/1056. Unmatched non-merge commits: 1. Merge base: `87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5`.

Non-identical branch-touched paths:

```text
mobile/src/api/league.ts
mobile/src/navigation/TabNav.tsx
mobile/src/screens/PortfolioScreen.tsx
mobile/src/screens/SettingsScreen.tsx
mobile/src/screens/TradesScreen.tsx
mobile/src/shared/types.ts
mobile/src/state/useSession.ts
```

</details>

<details><summary>feat/mobile-b4-trade-card-improvements — cd70e6a9e52b542d341c08be2d602fa99412273e</summary>

Tip subject: Mobile B4: Trade card reasons (flag-gated) + real/est badge + equal-only. Main A/B: 1/1056. Unmatched non-merge commits: 1. Merge base: `87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5`.

Non-identical branch-touched paths:

```text
mobile/src/api/trades.ts
mobile/src/components/FairnessSlider.tsx
mobile/src/components/TradeCard.tsx
mobile/src/screens/TradesScreen.tsx
mobile/src/shared/types.ts
```

</details>

<details><summary>feat/mobile-b5-trade-queue — dc781ff5495f35f06ce5f5214f25f941fb188c50</summary>

Tip subject: Bundle 5: mobile trade queue (flag trades.queue_2k). Main A/B: 1/1056. Unmatched non-merge commits: 1. Merge base: `87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5`.

Non-identical branch-touched paths:

```text
mobile/src/components/QueueChip.tsx
mobile/src/screens/TradesScreen.tsx
mobile/src/shared/types.ts
```

</details>

<details><summary>feat/mobile-b6-rookie-draft-board — f48108e79b157bc2aa6d85048bd47e3bbda1432d</summary>

Tip subject: Mobile B6: Rookie Draft Board sheet on Rank screen. Main A/B: 1/1056. Unmatched non-merge commits: 1. Merge base: `87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5`.

Non-identical branch-touched paths:

```text
mobile/src/api/rankings.ts
mobile/src/components/RookieDraftBoardSheet.tsx
mobile/src/screens/RankScreen.tsx
```

</details>

<details><summary>feat/mobile-b7-league-surfaces — 0eca32d978420915ef2b63d28f1654860d55a12b</summary>

Tip subject: Bundle 7: League surfaces (activity feed, contrarian leaderboard, unlock badges, new-partners banner). Main A/B: 1/1056. Unmatched non-merge commits: 1. Merge base: `87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5`.

Non-identical branch-touched paths:

```text
mobile/src/api/league.ts
mobile/src/components/ActivityFeed.tsx
mobile/src/components/ContrarianLeaderboard.tsx
mobile/src/components/NewPartnersBanner.tsx
mobile/src/screens/LeagueScreen.tsx
mobile/src/screens/TradesScreen.tsx
mobile/src/shared/types.ts
```

</details>

<details><summary>feat/mobile-b8-growth-loop — 6c45fdb17c4e64ee02318b8cfdfe07154706c627</summary>

Tip subject: Bundle 8: Growth loop — smart-start, try-demo, referral capture, public profile. Main A/B: 1/1056. Unmatched non-merge commits: 1. Merge base: `87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5`.

Non-identical branch-touched paths:

```text
mobile/App.tsx
mobile/src/api/auth.ts
mobile/src/navigation/RootNav.tsx
mobile/src/screens/ProfileScreen.tsx
mobile/src/screens/SignInScreen.tsx
mobile/src/shared/types.ts
mobile/src/state/useSession.ts
mobile/src/utils/deepLinks.ts
```

</details>

<details><summary>feat/notifications-clear-button-v2 — 3db8d31cc270c2ec782eef04dd3ac0c6e8973118</summary>

Tip subject: Add Clear button to notifications dropdown. Main A/B: 1/1079. Unmatched non-merge commits: 1. Merge base: `f93c76af239ea37b36e63f7d3ed4190a38b04eaf`.

Non-identical branch-touched paths:

```text
web/css/styles.css
web/index.html
web/js/app.js
```

</details>

<details><summary>feat/picker-select-all — a2214e9703cdb3ef878a5c5c0e30273a47582ce8</summary>

Tip subject: Find a Trade: add Select all / Clear all toggle to player picker. Main A/B: 1/1079. Unmatched non-merge commits: 1. Merge base: `f93c76af239ea37b36e63f7d3ed4190a38b04eaf`.

Non-identical branch-touched paths:

```text
web/css/styles.css
web/index.html
web/js/app.js
```

</details>

<details><summary>feat/sweep-followups-2026-08-18 — 74e880940a8ea5084378ffa153345b99ec8a0ea7</summary>

Tip subject: living-memory: close the force_fresh item (shipped in e8ae476); rebase onto bake-off Phase 0. Main A/B: 3/257. Unmatched non-merge commits: 3. Merge base: `9a20ca81afa0b509e5ce12edcecc87b21a161dba`.

Non-identical branch-touched paths:

```text
backend/database.py
backend/server.py
backend/tests/test_trade_decision_idempotency.py
docs/data-dictionary.md
living-memory/CHANGELOG.md
living-memory/DECISIONS.md
living-memory/GOTCHAS.md
living-memory/NEXT.md
living-memory/TEST_LEDGER.md
```

</details>

<details><summary>feat/trade-relevance-p0, origin/feat/trade-relevance-p0 — 03dbb2984e3daa89340ae92e88d388d8950f6cc9</summary>

Tip subject: recovery ledger: trade-relevance P0 build worktrees swept (join ef20d91, agg 7c89c09). Main A/B: 9/379. Unmatched non-merge commits: 7. Merge base: `21df73f64bdde4e3727e92eea1f3d30b3e584368`.

Non-identical branch-touched paths:

```text
backend/analytics_queries.py
backend/database.py
backend/feature_flags.py
backend/relevance/__init__.py
backend/relevance/batch.py
backend/relevance/config.py
backend/relevance/dedup.py
backend/relevance/passes/__init__.py
backend/relevance/passes/drift_check.py
backend/relevance/passes/flag_agg.py
backend/relevance/registry.py
backend/server.py
backend/taste_service.py
backend/tests/test_class_demotion.py
backend/tests/test_deck_dedup.py
backend/tests/test_deck_replenishment.py
backend/tests/test_disposition_join.py
backend/tests/test_gate_counters.py
backend/tests/test_p0_schema.py
backend/tests/test_pass_ledger.py
backend/tests/test_propensity_freeze.py
backend/tests/test_relevance_batch.py
backend/tests/test_relevance_config.py
backend/trade_optimizer.py
backend/trade_service.py
docs/api-reference.md
docs/architecture.md
docs/config-reference.md
docs/data-dictionary.md
docs/glossary.md
docs/plans/tiktok-discovery/current-state.md
docs/plans/trade-relevance-engine/lld.md
docs/plans/trade-relevance-engine/scope.md
docs/recovery/2026-08-14-trade-relevance-p0-worktree-sweep.md
docs/runbook.md
living-memory/CHANGELOG.md
living-memory/DECISIONS.md
living-memory/GOTCHAS.md
living-memory/HANDOFF.md
living-memory/NEXT.md
living-memory/TEST_LEDGER.md
```

</details>

<details><summary>feat/wave1-perf, origin/feat/wave1-perf — c30f4f1d59ca9256c673a7bc44de7b9d785a8328</summary>

Tip subject: Wave 1 perf: boot decouple, cold-cache, ELO memo, prefetch, timeout, throttle, index. Main A/B: 2/1030. Unmatched non-merge commits: 1. Merge base: `a1142da0c20d3492d12b6234ae2e082816de249b`.

Non-identical branch-touched paths:

```text
backend/database.py
backend/ranking_service.py
backend/server.py
backend/tests/test_elo_memoization.py
docs/code-audit/perf-optimization/README.md
docs/code-audit/perf-optimization/design/hld.md
docs/code-audit/perf-optimization/design/lld.md
docs/code-audit/perf-optimization/design/requirements/README.md
docs/code-audit/perf-optimization/design/requirements/init-01-splash-decouple.md
docs/code-audit/perf-optimization/design/requirements/init-02-coldstart-cache.md
docs/code-audit/perf-optimization/design/requirements/init-03-elo-memoization.md
docs/code-audit/perf-optimization/design/requirements/init-04-nav-prefetch.md
docs/code-audit/perf-optimization/design/requirements/init-05-focus-online-manager.md
docs/code-audit/perf-optimization/design/requirements/init-06-touch-activity-throttle.md
docs/code-audit/perf-optimization/design/requirements/init-07-persisted-cache-keys.md
docs/code-audit/perf-optimization/design/requirements/init-08-session-init-optimistic.md
docs/code-audit/perf-optimization/design/requirements/init-09-trade-gen-prune.md
docs/code-audit/perf-optimization/design/requirements/init-10-web-player-payload.md
docs/code-audit/perf-optimization/design/requirements/init-11-render-memo-virtualization.md
docs/code-audit/perf-optimization/design/requirements/init-12-api-client-resilience.md
docs/code-audit/perf-optimization/design/requirements/init-13-poll-backoff.md
docs/code-audit/perf-optimization/design/requirements/init-14-db-hygiene.md
docs/code-audit/perf-optimization/design/requirements/init-15-compression-docs.md
docs/code-audit/perf-optimization/design/requirements/init-16-league-activity-dedup.md
docs/code-audit/perf-optimization/observations/agent-01-api-client/findings.md
docs/code-audit/perf-optimization/observations/agent-02-data-fetching-cache/findings.md
docs/code-audit/perf-optimization/observations/agent-03-backend-routes/findings.md
docs/code-audit/perf-optimization/observations/agent-04-backend-data-db/findings.md
docs/code-audit/perf-optimization/observations/agent-05-rn-rendering/findings.md
docs/code-audit/perf-optimization/observations/agent-06-network-coldstart/findings.md
docs/code-audit/perf-optimization/observations/agent-06-network-coldstart/measurements.md
docs/code-audit/perf-optimization/plan/optimization-plan.md
docs/code-audit/perf-optimization/plan/priority-matrix.md
docs/code-audit/perf-optimization/research/00-research-methodology.md
docs/code-audit/perf-optimization/research/01-mobile-data-fetching.md
docs/code-audit/perf-optimization/research/02-backend-api-performance.md
docs/code-audit/perf-optimization/research/03-caching-strategies.md
docs/code-audit/perf-optimization/research/04-rn-rendering-list-perf.md
docs/code-audit/perf-optimization/research/05-network-coldstart.md
docs/code-audit/perf-optimization/templates/observation-template.md
docs/code-audit/perf-optimization/templates/recommendation-example.md
docs/code-audit/perf-optimization/templates/scoring-criteria.md
docs/plans/archive/2026/feedback-backend-sync/plan.md
docs/plans/archive/2026/mobile-feature-parity/artifacts/architecture-pre-protocol.md
mobile/App.tsx
mobile/src/api/auth.ts
mobile/src/api/client.ts
mobile/src/api/sleeper.ts
mobile/src/navigation/TabNav.tsx
mobile/src/state/useFeatureFlags.ts
```

</details>

<details><summary>fix/account-menu-hover-bridge — dfcb0f5699a60135c93cb408a97cd3b1d41c5cc5</summary>

Tip subject: Fix account menu hover gap that hid the dropdown mid-traverse. Main A/B: 1/1079. Unmatched non-merge commits: 1. Merge base: `f93c76af239ea37b36e63f7d3ed4190a38b04eaf`.

Non-identical branch-touched paths:

```text
web/css/styles.css
```

</details>

<details><summary>fix/league-summary-include-self-in-joined-count — 10a2d9bed0e9fed75eccfc137caaf72974efc55f</summary>

Tip subject: Fix: include logged-in user in League Summary "Leaguemates Joined" count. Main A/B: 1/1079. Unmatched non-merge commits: 1. Merge base: `f93c76af239ea37b36e63f7d3ed4190a38b04eaf`.

Non-identical branch-touched paths:

```text
web/js/app.js
```

</details>

<details><summary>fix/manual-rankings-remove-kebab-col — 53308eece16226ffbcc7a068171945d3408e6b4b</summary>

Tip subject: Remove dead kebab/three-dots column from Manual Rankings page. Main A/B: 1/1079. Unmatched non-merge commits: 1. Merge base: `f93c76af239ea37b36e63f7d3ed4190a38b04eaf`.

Non-identical branch-touched paths:

```text
web/css/styles.css
web/index.html
web/js/app.js
```

</details>

<details><summary>fix/tiers-manual-routing — c5397b4b36e240f44c6498fa39e3810b07341601</summary>

Tip subject: Fix: Tiers Manual link routes to Manual ranking, not Trios. Main A/B: 1/1079. Unmatched non-merge commits: 1. Merge base: `f93c76af239ea37b36e63f7d3ed4190a38b04eaf`.

Non-identical branch-touched paths:

```text
web/js/app.js
```

</details>

<details><summary>fix/trios-remove-college — 085fb777c50e91039f51ce9999951f6a4a6eaeea</summary>

Tip subject: Trios tiles: remove college metadata line. Main A/B: 1/1079. Unmatched non-merge commits: 1. Merge base: `f93c76af239ea37b36e63f7d3ed4190a38b04eaf`.

Non-identical branch-touched paths:

```text
web/js/app.js
```

</details>

<details><summary>fix/trios-remove-info-icon-2026-04-26 — bd33082d0d125f2ff17088b3f84618e07b1b71d5</summary>

Tip subject: Remove unnecessary info icon from Trios tile. Main A/B: 1/1079. Unmatched non-merge commits: 1. Merge base: `f93c76af239ea37b36e63f7d3ed4190a38b04eaf`.

Non-identical branch-touched paths:

```text
web/js/app.js
```

</details>

<details><summary>fix/trios-subtab-active-highlight — 472b3aa359d90394eb6f4d06a663f5ce05eda29f</summary>

Tip subject: Fix: highlight Trios sub-tab on default Rank Players landing. Main A/B: 1/1079. Unmatched non-merge commits: 1. Merge base: `f93c76af239ea37b36e63f7d3ed4190a38b04eaf`.

Non-identical branch-touched paths:

```text
web/index.html
```

</details>

<details><summary>fix/web-phase0 — 40390013672cae0079276ceb79b9e85146c13626</summary>

Tip subject: living-memory: record the merge, the gates, and the four operator calls. Main A/B: 8/66. Unmatched non-merge commits: 7. Merge base: `867c3baaee6c5a6a4de417d2892f8c4a35a4d9ee`.

Non-identical branch-touched paths:

```text
backend/server.py
docs/api-reference.md
docs/plans/README.md
docs/plans/web-parity/plan.md
docs/plans/web-parity/scope.md
docs/reviews/CLAUDE.md
living-memory/CHANGELOG.md
living-memory/DECISIONS.md
living-memory/GOTCHAS.md
living-memory/HANDOFF.md
living-memory/TEST_LEDGER.md
qa/web/check_web_structure.py
web/CLAUDE.md
web/css/styles.css
web/index.html
web/js/app.js
web/js/events.js
web/robots.txt
web/sitemap.xml
```

</details>

<details><summary>infra/render-cron-migration, origin/infra/render-cron-migration — 57300ae55db004d9981e4c375972701078459091</summary>

Tip subject: infra: move cron scheduling off Render blueprint to GitHub Actions. Main A/B: 1/531. Unmatched non-merge commits: 1. Merge base: `ea19d4b75cc9de1bf33d48d615678b8bd8356715`.

Non-identical branch-touched paths:

```text
.github/workflows/render-cron.yml
docs/runbook.md
render.yaml
```

</details>

<details><summary>mobile/yellow-followups — f7aa97752d5d3f96635cf39d37d70576ca236fbf</summary>

Tip subject: Refresh push permission status on app foreground. Main A/B: 2/1086. Unmatched non-merge commits: 2. Merge base: `8ebf2d96913b9e5340e9e9596924fdb1a122459c`.

Non-identical branch-touched paths:

```text
mobile/src/hooks/usePushNotifications.ts
mobile/src/navigation/RootNav.tsx
mobile/src/screens/LeagueScreen.tsx
mobile/src/screens/MatchesScreen.tsx
mobile/src/screens/TradesScreen.tsx
mobile/src/state/useNotifications.ts
mobile/src/state/useSession.ts
```

</details>

<details><summary>p1-remediation-2026-08-11 — 5a4a63217cb824ddcb3202e1f5af75552b496cac</summary>

Tip subject: docs(p1-9): trade_found across the reference layer + three living-memory decisions. Main A/B: 7/425. Unmatched non-merge commits: 7. Merge base: `7dfcd168d5e7fe0609e2533d779a691c41e09a43`.

Non-identical branch-touched paths:

```text
backend/analytics_taxonomy.py
backend/database.py
backend/feature_flags.py
backend/server.py
backend/tests/fixtures/flags/onboarding-v2.json
backend/tests/fixtures/flags/profiles-on.json
backend/tests/fixtures/flags/release-300.json
backend/tests/fixtures/flags/release.json
backend/tests/test_analytics_p0.py
backend/tests/test_events_api.py
backend/tests/test_trade_found.py
backend/trade_service.py
config/features.json
docs/api-reference.md
docs/business/analytics/2026-07-17-tracking-plan-v2.md
docs/config-reference.md
docs/cross-client-invariants.md
docs/data-dictionary.md
docs/glossary.md
docs/integrations/sleeper.md
docs/plans/archive/2026/audit-p1-remediation/DECISIONS-p1.md
docs/plans/archive/2026/mobile-testing/lld.md
docs/runbook.md
living-memory/DECISIONS.md
living-memory/LLD.md
living-memory/TEST_LEDGER.md
mobile/src/components/PushPrimingModal.tsx
mobile/src/components/SendInSleeperButton.tsx
mobile/src/components/TopBar.tsx
mobile/src/hooks/usePushNotifications.ts
mobile/src/navigation/RootNav.tsx
mobile/src/screens/SettingsScreen.tsx
mobile/src/screens/SleeperConnectScreen.tsx
mobile/src/utils/deepLinks.ts
```

</details>

<details><summary>rescue/session-gate-and-207-docs — 244d151c38468760a67a594315a84425434fce0a</summary>

Tip subject: recover push-permission banner and two Chalkline primitives from dead branches. Main A/B: 2/630. Unmatched non-merge commits: 2. Merge base: `fc260dea52f39590f4e8b3ac100e83a0d4a5c424`.

Non-identical branch-touched paths:

```text
docs/feedback/items/207-rookie-draft-detection/plan.md
docs/feedback/items/207-rookie-draft-detection/research-codebase.md
docs/feedback/items/207-rookie-draft-detection/research-platforms.md
mobile/src/components/PushPermissionBanner.tsx
mobile/src/components/chalkline/SegmentedTabs.tsx
mobile/src/components/chalkline/Spinner.tsx
mobile/src/components/chalkline/index.ts
mobile/src/hooks/usePushNotifications.ts
mobile/src/screens/LeagueScreen.tsx
mobile/src/screens/ManualRanksScreen.tsx
mobile/src/screens/PickAnchorScreen.tsx
mobile/src/screens/QuickRankScreen.tsx
mobile/src/screens/QuickSetTiersScreen.tsx
mobile/src/screens/RankScreen.tsx
mobile/src/screens/TiersScreen.tsx
mobile/src/state/useNotifications.ts
```

</details>

<details><summary>review/fit-challenger-eng — a140eca8e82e461e5af8221f7ab169213efd2f6a</summary>

Tip subject: review: drop prod dry-run output containing real usernames. Main A/B: 5/158. Unmatched non-merge commits: 5. Merge base: `fe191f6605d23a2a5252d8c445769ba20a321864`.

Non-identical branch-touched paths:

```text
.gitignore
backend/bakeoff_runner.py
backend/server.py
backend/tests/test_bakeoff_arm_a_golden.py
backend/tests/test_bakeoff_composition.py
backend/tests/test_trade_gen_fit.py
backend/trade_gen_fit.py
backend/trade_service.py
docs/adr/README.md
docs/adr/adr-013-fit-challenger-is-a-generator.md
docs/api-reference.md
docs/config-reference.md
docs/data-dictionary.md
docs/plans/README.md
docs/plans/fit-challenger/PRD.md
docs/plans/fit-challenger/README.md
docs/plans/fit-challenger/scope.md
docs/plans/three-model-bakeoff/PLAN.md
living-memory/CHANGELOG.md
living-memory/DECISIONS.md
living-memory/HANDOFF.md
living-memory/LLD.md
living-memory/NEXT.md
living-memory/TEST_LEDGER.md
reviewer-scaffolding/README.md
reviewer-scaffolding/arm_timing_fixture.py
reviewer-scaffolding/budget_probe.py
reviewer-scaffolding/inertness_probe.py
reviewer-scaffolding/prod_dryrun.py
reviewer-scaffolding/scale_probe.py
```

</details>

<details><summary>send-in-mfl — 1ea7c793e197659ff7ec4a89a16ac592bf32cc24</summary>

Tip subject: send-in-mfl: living-memory — LLD convention, D-025, TEST_LEDGER entry. Main A/B: 6/499. Unmatched non-merge commits: 6. Merge base: `ab9368f81aa580a007cc49c91240754206d3e1ec`.

Non-identical branch-touched paths:

```text
backend/feature_flags.py
backend/mfl_write.py
backend/server.py
backend/tests/fixtures/flags/all-on.json
backend/tests/fixtures/flags/onboarding-v2.json
backend/tests/fixtures/flags/profiles-on.json
backend/tests/fixtures/flags/release.json
backend/tests/fixtures/profiles/mfl.json
backend/tests/fixtures/seed_ui_test_db.py
backend/tests/test_mfl_propose_route.py
backend/tests/test_mfl_write.py
backend/tests/test_pick_assignment.py
config/features.json
docs/api-reference.md
docs/config-reference.md
docs/integrations/mfl.md
docs/plans/send-in-mfl/scope.md
docs/plans/send-in-mfl/spike-findings.md
living-memory/DECISIONS.md
living-memory/LLD.md
living-memory/TEST_LEDGER.md
archive/retired-tooling/mobile/maestro/flows/send-in-mfl.yaml
mobile/scripts/testid-lint-allow.txt
mobile/src/api/CLAUDE.md
mobile/src/api/sendInMfl.ts
mobile/src/components/CLAUDE.md
mobile/src/components/SendInSleeperButton.tsx
mobile/src/navigation/RootNav.tsx
mobile/src/screens/CLAUDE.md
mobile/src/screens/MflConnectScreen.tsx
```

</details>

<details><summary>session-2026-08-13-notif-ship — 05e87d848aced60a094b6e0f8891b3b01d5d94a8</summary>

Tip subject: docs: lock app name as Fleeced (D-048); icon masters + pre-launch checklist. Main A/B: 9/421. Unmatched non-merge commits: 8. Merge base: `3b64a4406d7fb9877169f9ae5ed87bbc7f4d1d3c`.

Non-identical branch-touched paths:

```text
backend/analytics_queries.py
backend/analytics_taxonomy.py
backend/database.py
backend/server.py
backend/tests/test_analytics_p0.py
docs/api-reference.md
docs/business/ops/app-store-prelaunch-checklist.md
docs/business/product/2026-08-13-dynasty-year-in-review-plan.md
docs/cross-client-invariants.md
docs/data-dictionary.md
docs/design/brand/README.md
docs/design/brand/fleeced-icon-masters/badsplit.png
docs/design/brand/fleeced-icon-masters/fleeced-sheep-3d.png
docs/design/brand/fleeced-icon-masters/fleeced-sheep-flat.png
docs/design/brand/fleeced-icon-masters/ram-chalk-head.png
docs/design/brand/fleeced-icon-masters/ram-mohawk-laces.png
docs/design/brand/fleeced-icon-masters/ram-mohawk-pinkeyes-1.png
docs/design/brand/fleeced-icon-masters/ram-mohawk-pinkeyes-2.png
docs/design/brand/fleeced-icon-masters/ram-mohawk-pinkeyes-glow.png
docs/design/brand/fleeced-icon-masters/ram-pigskin-head.png
docs/design/brand/fleeced-icon-masters/ram-pinkeyes-mouth-1.png
docs/design/brand/fleeced-icon-masters/ram-pinkeyes-mouth-2.png
docs/design/brand/fleeced-icon-masters/ram-pinkeyes-mouth-glow.png
docs/design/brand/fleeced-icon-masters/ram-pinkhorn-pigskin.png
docs/design/brand/fleeced-icon-masters/vesica.png
docs/design/brand/naming-program-contact-sheet.png
docs/glossary.md
living-memory/CHANGELOG.md
living-memory/DECISIONS.md
living-memory/HANDOFF.md
living-memory/LLD.md
living-memory/NEXT.md
living-memory/TEST_LEDGER.md
mobile/package.json
mobile/src/components/TopBar.tsx
mobile/src/utils/deepLinks.ts
mobile/tests/check-notif-glyphs.js
web/js/app.js
```

</details>

<details><summary>spike/send-in-espn-write — 17eb62b618d3d38db00ead88b70c5b4c53bb76c1</summary>

Tip subject: spike(espn): scaffold Send-in-ESPN write module + verification plan + reversal draft. Main A/B: 1/499. Unmatched non-merge commits: 1. Merge base: `ab9368f81aa580a007cc49c91240754206d3e1ec`.

Non-identical branch-touched paths:

```text
backend/espn_write.py
backend/feature_flags.py
backend/tests/test_espn_write.py
docs/plans/espn-send-decision-reversal-draft-2026-08-11.md
docs/plans/espn-send-spike-verification-2026-08-11.md
```

</details>

<details><summary>teardown-remediation — 30492ac73d5a70dc5ebdb8614a43d55887508648</summary>

Tip subject: analytics: prod tooling, dashboard rebuild, and three client fixes found in prod data. Main A/B: 4/706. Unmatched non-merge commits: 2. Merge base: `20548ff36ec6290d1c578c71b34639018eddde94`.

Non-identical branch-touched paths:

```text
backend/analytics_queries.py
backend/analytics_taxonomy.py
backend/database.py
backend/server.py
backend/tests/test_events_api.py
docs/api-reference.md
docs/business/analytics/2026-07-17-tracking-plan-v2.md
docs/data-dictionary.md
docs/feedback/items/207-rookie-draft-detection/plan.md
docs/feedback/items/207-rookie-draft-detection/research-codebase.md
docs/feedback/items/207-rookie-draft-detection/research-platforms.md
docs/plans/archive/2026/rookie-draft/hld.md
docs/plans/archive/2026/rookie-draft/lld.md
docs/plans/archive/2026/rookie-draft/plan.md
docs/runbook.md
mobile/src/api/client.ts
mobile/src/api/events.ts
mobile/src/screens/ManualRanksScreen.tsx
mobile/src/screens/PickAnchorScreen.tsx
mobile/src/screens/QuickRankScreen.tsx
mobile/src/screens/QuickSetTiersScreen.tsx
mobile/src/screens/RankScreen.tsx
mobile/src/screens/TiersScreen.tsx
mobile/src/state/useSession.ts
web/js/events.js
```

</details>

<details><summary>worktree-agent-a05d00e6 — dddb1ff826951616286af3e854043e59dff2d63e</summary>

Tip subject: League Summary: leaguemates roster section with Invite button (top-right). Main A/B: 1/1079. Unmatched non-merge commits: 1. Merge base: `f93c76af239ea37b36e63f7d3ed4190a38b04eaf`.

Non-identical branch-touched paths:

```text
backend/server.py
web/css/styles.css
web/index.html
web/js/app.js
```

</details>

<details><summary>worktree-agent-a651d045 — 4da6011312b0dc0d446cbc58694e628d0ea9bdb3</summary>

Tip subject: League Summary: in-place dropdown to switch active league. Main A/B: 1/1079. Unmatched non-merge commits: 1. Merge base: `f93c76af239ea37b36e63f7d3ed4190a38b04eaf`.

Non-identical branch-touched paths:

```text
web/css/styles.css
web/index.html
web/js/app.js
```

</details>

<details><summary>worktree-agent-a729a704 — 76c4ae0e2d992cd828ce56fd3bae76cde89519cb</summary>

Tip subject: Fix Trends page never loading data on nav click. Main A/B: 1/1079. Unmatched non-merge commits: 1. Merge base: `f93c76af239ea37b36e63f7d3ed4190a38b04eaf`.

Non-identical branch-touched paths:

```text
web/js/app.js
```

</details>

<details><summary>worktree-agent-a9b33518 — 1485c1727a5b630932ba806fc874d0af2f3b3fbc</summary>

Tip subject: Replace ELO column with Tier on Manual Ranking table. Main A/B: 1/1079. Unmatched non-merge commits: 1. Merge base: `f93c76af239ea37b36e63f7d3ed4190a38b04eaf`.

Non-identical branch-touched paths:

```text
web/index.html
web/js/app.js
```

</details>

<details><summary>worktree-agent-a9c4c705ebb53fc71 — 60aa45721ae5419a218027674471adedf46aa5df</summary>

Tip subject: PROTOTYPE (do not merge): v3_pool_fit_extra roster-fit pool term + falsification fixture. Main A/B: 1/19. Unmatched non-merge commits: 1. Merge base: `ce3f443cd7e1dcc43e82288cbfc1c2407792f488`.

Non-identical branch-touched paths:

```text
backend/tests/test_bakeoff_arm_a_golden.py
backend/tests/test_v3_pool_fit_prototype.py
backend/trade_optimizer.py
backend/trade_service.py
```

</details>

<details><summary>worktree-agent-ab5ed8ed — 7730729b6cb6f58f81c65f8e36946320fb1efe23</summary>

Tip subject: Restore Trends subtab on positional-tiers page. Main A/B: 1/1079. Unmatched non-merge commits: 1. Merge base: `f93c76af239ea37b36e63f7d3ed4190a38b04eaf`.

Non-identical branch-touched paths:

```text
web/positional-tiers.html
```

</details>

<details><summary>worktree-agent-ad7046bc — 90cb01edde8474646ceaaf74ef8dceefc0cc8a43</summary>

Tip subject: Match notifications: drop redundant emoji from body. Main A/B: 1/1079. Unmatched non-merge commits: 1. Merge base: `f93c76af239ea37b36e63f7d3ed4190a38b04eaf`.

Non-identical branch-touched paths:

```text
backend/server.py
web/js/app.js
```

</details>

<details><summary>worktree-agent-ade0db7c — ff9f88b889bb94d8759cf848854cd0e01234f7fd</summary>

Tip subject: Web: render initial Trio on auto-auth (don't wait for tab switch). Main A/B: 1/1079. Unmatched non-merge commits: 1. Merge base: `f93c76af239ea37b36e63f7d3ed4190a38b04eaf`.

Non-identical branch-touched paths:

```text
web/js/app.js
```

</details>

<details><summary>origin/claude/stoic-mccarthy-e56da9 — 71076178ea3e3e3945b3ca208bb5a799c8d4241c</summary>

Tip subject: mobile: fix Depth tier color to match cross-client invariant (purple #a855f7). Main A/B: 1/999. Unmatched non-merge commits: 1. Merge base: `33496d8217e946c517f87a3526db0dfa9dd0a344`.

Non-identical branch-touched paths:

```text
mobile/src/components/TierBadge.tsx
mobile/src/components/TierBin.tsx
mobile/src/theme/colors.ts
```

</details>

<details><summary>origin/claude/team-review-analysis-plan-1f91e3 — 34cb825f518370e97679ff45f1d369121dbf943f</summary>

Tip subject: living-memory: record the odds-shift + Team Review build session. Main A/B: 1/154. Unmatched non-merge commits: 1. Merge base: `a76498efdc3753edf07284c09b2d0e0561648fdf`.

Non-identical branch-touched paths:

```text
living-memory/CHANGELOG.md
```

</details>

<details><summary>origin/docs/card-evidence — 92ea29c071412c54380627768d383b5f5a6a6b06</summary>

Tip subject: docs: card-evidence PRD (verdict, impact, comps). Main A/B: 1/206. Unmatched non-merge commits: 1. Merge base: `50e0451d4db14f91535479c84ae9a42113037900`.

Non-identical branch-touched paths:

```text
docs/plans/README.md
docs/plans/card-evidence/PRD.md
docs/plans/card-evidence/README.md
docs/plans/card-evidence/scope.md
```

</details>

<details><summary>origin/docs/fit-challenger — 52414d8696d53305b5b0cabdd1ec6d1778dfd722</summary>

Tip subject: docs: fit-challenger PRD (thin knockouts, dual 0-100 scores). Main A/B: 1/189. Unmatched non-merge commits: 1. Merge base: `2a492b690f38b577bde191efcc3acc00bdb6f07f`.

Non-identical branch-touched paths:

```text
docs/plans/README.md
docs/plans/fit-challenger/PRD.md
docs/plans/fit-challenger/scope.md
```

</details>

<details><summary>origin/docs/landability-challenger — 23fee85a2708eb60fcdf9640196d812605b1ed0a</summary>

Tip subject: docs: landability challenger PRD (bake-off arm D). Main A/B: 1/206. Unmatched non-merge commits: 1. Merge base: `50e0451d4db14f91535479c84ae9a42113037900`.

Non-identical branch-touched paths:

```text
docs/plans/README.md
docs/plans/landability-challenger/PRD.md
docs/plans/landability-challenger/README.md
docs/plans/landability-challenger/scope.md
docs/plans/three-model-bakeoff/PLAN.md
```

</details>

<details><summary>origin/docs/ppg-impact — 644a6676165e4a87b123e9fba0f092f89b0d5c65</summary>

Tip subject: docs: starter PPG delta PRD (Sleeper proj + nflverse). Main A/B: 1/206. Unmatched non-merge commits: 1. Merge base: `50e0451d4db14f91535479c84ae9a42113037900`.

Non-identical branch-touched paths:

```text
docs/plans/README.md
docs/plans/ppg-impact/PRD.md
docs/plans/ppg-impact/README.md
docs/plans/ppg-impact/scope.md
```

</details>

<details><summary>origin/feat/fit-challenger — 33c649ba97f4f1e5d1e3794f4144673ab709a6a8</summary>

Tip subject: feat: fit-challenger generator (bake-off arm `fit`, default off). Main A/B: 2/189. Unmatched non-merge commits: 2. Merge base: `2a492b690f38b577bde191efcc3acc00bdb6f07f`.

Non-identical branch-touched paths:

```text
backend/bakeoff_runner.py
backend/server.py
backend/tests/test_bakeoff_arm_a_golden.py
backend/tests/test_bakeoff_composition.py
backend/tests/test_trade_gen_fit.py
backend/trade_gen_fit.py
backend/trade_service.py
docs/adr/README.md
docs/adr/adr-013-fit-challenger-is-a-generator.md
docs/api-reference.md
docs/config-reference.md
docs/data-dictionary.md
docs/plans/README.md
docs/plans/fit-challenger/PRD.md
docs/plans/fit-challenger/README.md
docs/plans/fit-challenger/scope.md
docs/plans/three-model-bakeoff/PLAN.md
living-memory/CHANGELOG.md
living-memory/DECISIONS.md
living-memory/HANDOFF.md
living-memory/LLD.md
living-memory/NEXT.md
living-memory/TEST_LEDGER.md
```

</details>

<details><summary>origin/fix/tiers-rework — 65bb39ad04369702a133aef44f4b3d80fb6087fd</summary>

Tip subject: Tiers multi-select: stop bulk-move from dragging non-selected players across tiers. Main A/B: 6/1012. Unmatched non-merge commits: 5. Merge base: `bb3636ea69c88b515b942f22b4065cc6cc1e220d`.

Non-identical branch-touched paths:

```text
mobile/src/screens/TiersScreen.tsx
```

</details>

## Proposed commands and recovery ledger entries

These are exact targets, captured before deletion. **Do not rerun already completed operations.** The executor must first append the selected tip rows to `docs/recovery/2026-09-04-branch-cleanup.md`, cite this audit, and record actual deletion date/result. Preserve non-main-reachable tips under recovery refs or a bundle if durable recovery is desired; a SHA written in a document alone does not prevent Git garbage collection.

Immediately before each local deletion, require its current tip to equal the recorded SHA and verify it is not owned by any current worktree; `git branch -D` supplies an additional checked-out-branch refusal. Never force a worktree removal without inspecting and preserving its untracked/ignored material. The parent observed and handled a real ownership race in this pass.

Local branch command manifest (full expected SHA is a precondition; commands are deliberately not auto-executed by this report):

```sh
# expected 45a2520c36778771190ba3e6cf34e96cc6bbaf41
git branch -D -- 'audit/armb-claims-1-2'
# expected b2e794f94ba1f0dc37105e09d3ba61289f7d286d
git branch -D -- 'audit/armb-claims-3-4'
# expected 238cc3ee0963175f257d681cb1dfdd2000162ff3
git branch -D -- 'audit/armb-claims-5-6'
# expected d6b324194f7efad0878237bf6d0fa1133186eb00
git branch -D -- 'audit/armb-remedy-bucket-a'
# expected 79f7cc3ebdd994e9c8def2980574ff316becdfaf
git branch -D -- 'audit/armb-remedy-bucket-b'
# expected e873966e474746d127e41fb70c4a52da63e33582
git branch -D -- 'audit/armb-remedy-bucket-c'
# expected 7cb9a25b6809770d8d08406773d9cc1572cb5d2f
git branch -D -- 'audit/claim-7-armb'
# expected 9026da7702fcf4fc117c903c92dddd6f7c226cfa
git branch -D -- 'audit/consensus-gate-matrix'
# expected 307b8f8e120e60b912d6eed7d21dbef32595821a
git branch -D -- 'audit/knockout-waterfall'
# expected 63d2965d9d569f57aa4c480c5568239e6efb6cbd
git branch -D -- 'build-staging'
# expected 02e27dda7446dcf5289c2168776694d86d73395a
git branch -D -- 'chore/bakeoff-serve-interleaved'
# expected 4340b60473bc1ab6d39fd80f3d312ad4a6e8c778
git branch -D -- 'chore/session-wrapup'
# expected ba4a6ad1446acddbac468d94e52faf38036b46c8
git branch -D -- 'claude/372-window-composite'
# expected eb9c1dee7029a301d4bda535f12b380b8f80ddbc
git branch -D -- 'claude/agitated-sanderson-d9eaf9'
# expected 968d9a8e13a3ba9d730bb542498f5b8d4aea299f
git branch -D -- 'claude/awesome-northcutt-0a5093'
# expected 18f15f7ad36ca988ef364fc4d0041218f7313a52
git branch -D -- 'claude/busy-swartz-521ff5'
# expected 0edc7de7351a30fe0d4b8ee3068df31874bcda2d
git branch -D -- 'claude/clever-euler-49a334'
# expected 49cf21e5002ac77ea5978ba17431b4671c5ebcfc
git branch -D -- 'claude/compassionate-goldstine-410636'
# expected 49cf21e5002ac77ea5978ba17431b4671c5ebcfc
git branch -D -- 'claude/condescending-jemison-61ad0a'
# expected 37d74b2bd15174e35ebfa6381b97af14232e9389
git branch -D -- 'claude/cool-hermann'
# expected 0ad2fe9bc1c9f7cd69daf58aa0fdaa5de2a70c02
git branch -D -- 'claude/cranky-hofstadter-251429'
# expected bc340607b6f0a78e434cae2552f1ae31d94c4c52
git branch -D -- 'claude/crazy-noyce-6cdea0'
# expected e92f95c16034101f1d1f925b6e90b27273d62d4a
git branch -D -- 'claude/driver-setup-step-7-b50718'
# expected 9e1a8be1a6612ef2e6b6be99ef96bf46b2d33f27
git branch -D -- 'claude/elastic-kapitsa-c75ce7'
# expected 74cd664030ed2a3603a7d8a5f384e5fff7f3d836
git branch -D -- 'claude/exciting-bardeen-3a477c'
# expected cfe930018ee5ca66d5d67d679e8155d266f5d869
git branch -D -- 'claude/festive-mccarthy-b10c3a'
# expected 867c3baaee6c5a6a4de417d2892f8c4a35a4d9ee
git branch -D -- 'claude/finished-unmerged-worktrees-48b67b'
# expected af91d6f8225d662110e67188adee1705ce219d64
git branch -D -- 'claude/ftf-file-continuation-c9185e'
# expected c321958d77dd799087d1c556835dca0de4321b93
git branch -D -- 'claude/gifted-sanderson-0d3ca0'
# expected 69dc0cae7db1cd41a522dfb7d33f280038d318c2
git branch -D -- 'claude/goofy-perlman-490e49'
# expected d3fe3acbde5a4ce4dda42206cd2a9a848e6ee15b
git branch -D -- 'claude/hungry-bhaskara-0e11b2'
# expected dd893b85823614762f5d67ca269ccb4ad673f8c0
git branch -D -- 'claude/jolly-leakey-d20295'
# expected 355bddb3d044d502dbb86587188cd27859b7d342
git branch -D -- 'claude/jovial-meninsky-8bf0a0'
# expected 16a9b51d4ab84b37f3f8d4e1e98e7bbc8f64a67b
git branch -D -- 'claude/keen-varahamihira-8986d4'
# expected e92f95c16034101f1d1f925b6e90b27273d62d4a
git branch -D -- 'claude/league-mate-invite-sharing-26a697'
# expected 33496d8217e946c517f87a3526db0dfa9dd0a344
git branch -D -- 'claude/magical-cerf-7cfaca'
# expected 0ad2fe9bc1c9f7cd69daf58aa0fdaa5de2a70c02
git branch -D -- 'claude/magical-hofstadter-40cf12'
# expected 5dcf29f00f42ceca2351aa130074012ae7ea8e0f
git branch -D -- 'claude/modest-albattani-138a2d'
# expected 2f88aaba4cd565de335ee3ded2f9cc339b4cf089
git branch -D -- 'claude/mystifying-williamson-4595ad'
# expected 49cf21e5002ac77ea5978ba17431b4671c5ebcfc
git branch -D -- 'claude/nice-lovelace-83e5e8'
# expected a40eee89abe4ed0585e0bd5a58a43aa84bbd2385
git branch -D -- 'claude/nifty-shtern-6dbae1'
# expected 628f7b6001e78c2c1fc9f264af6e4723b87aad64
git branch -D -- 'claude/notif-crons'
# expected 1dd94681ebd748d99e4233486df86ed0212aee6a
git branch -D -- 'claude/notif-events'
# expected c7e756662f82fe6d48a0e03e6f73240b2d34fbd5
git branch -D -- 'claude/open-feedback-summary-b43796'
# expected e92f95c16034101f1d1f925b6e90b27273d62d4a
git branch -D -- 'claude/outstanding-work-summary-b10a36'
# expected 2529bef953c2a3f116fffe7b71fb4f4173695225
git branch -D -- 'claude/peaceful-lumiere-e2a25b'
# expected 0edc7de7351a30fe0d4b8ee3068df31874bcda2d
git branch -D -- 'claude/pensive-kilby-d53555'
# expected 5e758d66433a6ca5613b235eba6cc3c1e678627c
git branch -D -- 'claude/reverent-gagarin-ff2b57'
# expected 49cf21e5002ac77ea5978ba17431b4671c5ebcfc
git branch -D -- 'claude/sad-brown-d5ef76'
# expected 49cf21e5002ac77ea5978ba17431b4671c5ebcfc
git branch -D -- 'claude/sharp-hamilton-2ec655'
# expected e89eebb0fbedba03584b4cc99d0399f38ccf96e6
git branch -D -- 'claude/shoprite-grocery-cart-de3c37'
# expected f93c76af239ea37b36e63f7d3ed4190a38b04eaf
git branch -D -- 'claude/strange-jang-5fb4b7'
# expected 3e7e25cff497f006826664de4f2d187a59771748
git branch -D -- 'claude/team-outlook-experience-27a7a1'
# expected 9e1a8be1a6612ef2e6b6be99ef96bf46b2d33f27
git branch -D -- 'claude/trade-decisions-review-6786b1'
# expected af91d6f8225d662110e67188adee1705ce219d64
git branch -D -- 'claude/trade-disposition-review-89a94b'
# expected 867c3baaee6c5a6a4de417d2892f8c4a35a4d9ee
git branch -D -- 'claude/trade-verdict-elo-discrepancy-6e5606'
# expected 451d2ebd714033a3b1f6bba3fc1b939f9d086efb
git branch -D -- 'claude/trading-engine-eval-8ab7bc'
# expected 30070f3692cc08cd5dde8c96da2877642f4f73ca
git branch -D -- 'claude/vibrant-allen-023c8f'
# expected 33496d8217e946c517f87a3526db0dfa9dd0a344
git branch -D -- 'claude/vigilant-wozniak-382289'
# expected 867c3baaee6c5a6a4de417d2892f8c4a35a4d9ee
git branch -D -- 'claude/wait-instructions-ef2095'
# expected a93e5d861d94d220c423457afb4a88f8efb5eeb9
git branch -D -- 'claude/zealous-rubin'
# expected 950fc9795951114aae6fb51e67e6dd78d522a24f
git branch -D -- 'docs/armb-audit-consolidated'
# expected 613a34c3f55d4bd060c5b5ddf6a59a6f74e52bba
git branch -D -- 'docs/auditor-handoff'
# expected 4c0213b2a52f20e9aea7817aacffb703da39a9e7
git branch -D -- 'docs/session-memory-writeback'
# expected 38806e0328792f9fae70345244112ea8b661bb34
git branch -D -- 'feat/bakeoff-arm-a-challenger'
# expected bcee58a2c699bd004a28f226abe2e44ae2aea66a
git branch -D -- 'feat/decline-reason-player-pref'
# expected 2fa1ff24f0ceb143d7b23b79ed5ea874a218a619
git branch -D -- 'feat/espn-credential-verify'
# expected 66cd2eac050c02fd005a9b13e7d1b9cf072b6cea
git branch -D -- 'feat/feedback-backend-route'
# expected 66cd2eac050c02fd005a9b13e7d1b9cf072b6cea
git branch -D -- 'feat/feedback-mobile-sync'
# expected 23b19cb527c5693be797f87f6bfb0e2d1044299d
git branch -D -- 'feat/fleeced-identity'
# expected a362a15ad810b579d73940ffa0a485d1ec55ce86
git branch -D -- 'feat/light-tier-flags'
# expected 3af201ac7ddd3f18c58fe0f6d7c7fd39c9ccfd4e
git branch -D -- 'feat/mfl-send-integrated'
# expected 0e0095f22ac1516543c643194b11e5a9d3baa0ca
git branch -D -- 'feat/mfl-trade-lifecycle'
# expected 2105d53ba54ff16518631065c704dd868b3e6fc0
git branch -D -- 'feat/pick-slot-labels'
# expected 8b7689a0f3a060f9b826079e65e4bc0b1f7e19d4
git branch -D -- 'feat/pick-year-decay'
# expected 8b7689a0f3a060f9b826079e65e4bc0b1f7e19d4
git branch -D -- 'feat/pin-tier-clamp'
# expected 7f16217bf223b4307ecced5e074334d915478f2f
git branch -D -- 'feat/placement-tier-clamp'
# expected 3293f4aa1a9f6cddacce998ea0793578e31422ae
git branch -D -- 'feat/platform-unlink'
# expected e1532a71ac8d4e82f8c2e5d6c745153dc169376b
git branch -D -- 'feat/round2-pick-recalibration'
# expected 7315d8c62ec30ad47f2a27fdc7d6cbf5ef84aa05
git branch -D -- 'feat/send-auth-lazy'
# expected f89d8805c4ebd436705f5d59da1edc4fa9c2c82f
git branch -D -- 'feat/send-in-espn'
# expected 5cde107fd79b4753e02c3f14d80b6ab0d322b856
git branch -D -- 'feat/send-in-mfl'
# expected 45fb2cada5645f430d3b5241d77a11e78a6bb531
git branch -D -- 'feat/send-in-mfl-followups'
# expected 3b64a4406d7fb9877169f9ae5ed87bbc7f4d1d3c
git branch -D -- 'feat/sleeper-reachability-probe'
# expected f56216e5931d336051648b889c23700ce74a1398
git branch -D -- 'feat/team-review-batch-2'
# expected e423f602d8b795c442535b87eed6fdadbe83883f
git branch -D -- 'feat/trade-presentation-v2'
# expected bbc2e4b166925c4417bb5ec559a9241354b1b9fb
git branch -D -- 'feat/window-composite'
# expected c21c52071a0b7e89c317d2cd6d7b7643cd77bd62
git branch -D -- 'feedback-batch-2-base'
# expected bcd64e8f15abf70a2c33d8b8589ceb61b85b5c29
git branch -D -- 'feedback-fixes-2026-08-08'
# expected 31793d2326c549a17975afe9c0269b386f1967a2
git branch -D -- 'fix/armc-gen-v2-forfeits'
# expected 6f8daf407c51680188ada8063ab04cba24eb1cb5
git branch -D -- 'fix/bakeoff-outlook-lane'
# expected d755b3b95a62db2d8c186ff2392758d298c3a60a
git branch -D -- 'fix/balanced-claim-fairness-gate'
# expected a53b14259f94ef0d0eee487ff91b05879ce831e6
git branch -D -- 'fix/deck-give-headliner-cap'
# expected 7dfcd168d5e7fe0609e2533d779a691c41e09a43
git branch -D -- 'fix/espn-verification-oracle'
# expected bda0d51844b289dc509f84c71c8a44a15f742fac
git branch -D -- 'fix/finder-conditions-and-partners-copy'
# expected c451065c583d7313bc72dd73ea9df2dfca0037af
git branch -D -- 'fix/launch-privacy-legal'
# expected 7110af216b5037e1b2105bae149a4bf8ac66e208
git branch -D -- 'fix/likes-you-quality-gates'
# expected fc260dea52f39590f4e8b3ac100e83a0d4a5c424
git branch -D -- 'fix/pick-assignment-missing-user-team-clean'
# expected 2009de5996ed103530245ef8f695715c838bb885
git branch -D -- 'fix/pick-horizon'
# expected e777e9d4f1165d5aebf4877a7b101fdc60153929
git branch -D -- 'fix/pick-round3-value'
# expected 50e0451d4db14f91535479c84ae9a42113037900
git branch -D -- 'perf/dp-single-fetch'
# expected 33a51831a3d52f14a6b6661ea30432417ce95508
git branch -D -- 'rookie-draft/qa-flag-flip'
# expected ab9368f81aa580a007cc49c91240754206d3e1ec
git branch -D -- 'session-2026-08-10'
# expected ffd55f84ade5f8d248cfefd9c1e306830aca186d
git branch -D -- 'session-2026-08-11-169'
# expected fe191f6605d23a2a5252d8c445769ba20a321864
git branch -D -- 'ship/analysis'
# expected 24be3956f98d7c4cd4c4bd9285b64f9f8a6fd7f7
git branch -D -- 'ship/armed'
# expected 579a9e3db984a77b592bf0dc6966442bc47622b7
git branch -D -- 'ship/bakeoff-dark'
# expected a12240657e6d7442acc309766a6e8312e7ef8af1
git branch -D -- 'ship/bakeoff-interleave-on'
# expected 1bf064572ee79db11c7ee7ad84be6e4de6efb5b2
git branch -D -- 'ship/co-owner-ledger'
# expected a7f8783ee1ae84a942b21025a3065704ef616cf6
git branch -D -- 'ship/composition'
# expected a12240657e6d7442acc309766a6e8312e7ef8af1
git branch -D -- 'ship/disable-presentation'
# expected a130dfc2e4b0679f3479f1ba84c5fbd77fa366dd
git branch -D -- 'ship/engine-batch'
# expected 28c12a0a6b71212cf7f957d716c1f9360b6a5984
git branch -D -- 'ship/four-fixes'
# expected 19f6fe87ec5103307541f53cad43268e93dec29d
git branch -D -- 'ship/mobile-1150'
# expected 16d277f5c12a8d1c36b36534b74ac1cabe0df0a3
git branch -D -- 'ship/pick-fixes'
# expected 8b7689a0f3a060f9b826079e65e4bc0b1f7e19d4
git branch -D -- 'ship/pickyear'
# expected 66cd2eac050c02fd005a9b13e7d1b9cf072b6cea
git branch -D -- 'sync-main-temp'
# expected ca2b26aad6c695a662895fee8c5108fd291af200
git branch -D -- 'trade-engine-v2'
# expected bb3636ea69c88b515b942f22b4065cc6cc1e220d
git branch -D -- 'verify-batch-2'
# expected 1580064cb88cb2f86f0264b03f76d500e2266984
git branch -D -- 'worktree-agent-a064c586eb5fd3310'
# expected 791a6df3e4307530e7e823be60183a647b298425
git branch -D -- 'worktree-agent-a06e7515c090bf5ca'
# expected ab9368f81aa580a007cc49c91240754206d3e1ec
git branch -D -- 'worktree-agent-a073f9cfc8b08f4a0'
# expected 26f76f3baf7827ea49dfb001a4418f1ca669508f
git branch -D -- 'worktree-agent-a09286dd2a0cefc88'
# expected 87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5
git branch -D -- 'worktree-agent-a099babc74eec6d1a'
# expected f65bab75adf3a949c82402a4f0c6767166bcb142
git branch -D -- 'worktree-agent-a0bc3ef65ca534b5c'
# expected 35b63fc1dba4948ee7afb908cfaf401bbdc92e56
git branch -D -- 'worktree-agent-a0bdfe68ec9ca11b4'
# expected f93c76af239ea37b36e63f7d3ed4190a38b04eaf
git branch -D -- 'worktree-agent-a0c99997'
# expected 7d259d43936cf840b8c5987714162975e1308eac
git branch -D -- 'worktree-agent-a0d2eb20f30acda42'
# expected 3612d4331921c1e05dfe885a8dcd5c857db606ea
git branch -D -- 'worktree-agent-a13566f6f2eae60c6'
# expected 09a157620e25bfd9e0d8a9279787594012f692fb
git branch -D -- 'worktree-agent-a144f20a6bab9803f'
# expected 77b4a5033009c956f8eca557b920b401bdcbeb76
git branch -D -- 'worktree-agent-a150542a25adbf68e'
# expected 36618be8e1644047fd2e6037e359fde567c5d889
git branch -D -- 'worktree-agent-a16b8c9e20f110454'
# expected bb56c592bb76ce475e61f59ec9a53e06efbc82f9
git branch -D -- 'worktree-agent-a1de9f7cdca7d4cc9'
# expected f93c76af239ea37b36e63f7d3ed4190a38b04eaf
git branch -D -- 'worktree-agent-a209b4b5'
# expected f93c76af239ea37b36e63f7d3ed4190a38b04eaf
git branch -D -- 'worktree-agent-a2472651'
# expected 31c77310f4c19a9574bfa8954dd9b5cb06599df7
git branch -D -- 'worktree-agent-a25635d5055222d04'
# expected ab9368f81aa580a007cc49c91240754206d3e1ec
git branch -D -- 'worktree-agent-a2831e3434378f02f'
# expected ffda9af2860eefd74534a1e52be4d7d50c727e7d
git branch -D -- 'worktree-agent-a28505c47f2b4ed52'
# expected 0eb1061b16c1bcf1ccdc6568ef4fc11cfe605f1b
git branch -D -- 'worktree-agent-a28555e49939cb179'
# expected deaa6b27fcf3d084b0ef1f3fa3c0af3b295d6db6
git branch -D -- 'worktree-agent-a28a3f476f5095e4e'
# expected bcd64e8f15abf70a2c33d8b8589ceb61b85b5c29
git branch -D -- 'worktree-agent-a28d45a9c473696b2'
# expected f93c76af239ea37b36e63f7d3ed4190a38b04eaf
git branch -D -- 'worktree-agent-a2953877'
# expected 68920c3fa0c2195b6b9ea78c52e224dfadfc3f3c
git branch -D -- 'worktree-agent-a2a643a810416fc64'
# expected 6c008c31db12662fa8a453e7d88390920a1d42a6
git branch -D -- 'worktree-agent-a2c3e26232f8d0fd3'
# expected 0106aba4847ecc0a90241411390b2516d3f20fb8
git branch -D -- 'worktree-agent-a2eaddb5b4dcb9f75'
# expected 023f747a7f5d8fd7590fab82ff836b1f9d6706d8
git branch -D -- 'worktree-agent-a302dd30809085cce'
# expected 62ff8d68221ce126f405e0fefbe9bb90b28cce45
git branch -D -- 'worktree-agent-a3079a842e541927e'
# expected 048e918c7cea52acfc8ffddae089d7655c994b1d
git branch -D -- 'worktree-agent-a30c874ee2bdc0aa2'
# expected 78d4bb399fb51ad1e10f1b9236debe84642f00a6
git branch -D -- 'worktree-agent-a323bd5a940b685f9'
# expected f93c76af239ea37b36e63f7d3ed4190a38b04eaf
git branch -D -- 'worktree-agent-a3373f13'
# expected f01ac9f80e8b2bdd8e799fc22ad9cd945229bde6
git branch -D -- 'worktree-agent-a3528c7ae653aa236'
# expected e263490f46e38a6bb15754fda14f04db6f6a58d9
git branch -D -- 'worktree-agent-a368c8b0276754b90'
# expected fc260dea52f39590f4e8b3ac100e83a0d4a5c424
git branch -D -- 'worktree-agent-a36aaf8ad623b3be3'
# expected b2bd07894a6dd67c25f21f0c2dc036332a75afc4
git branch -D -- 'worktree-agent-a37f0a74fe2ac8b03'
# expected ec25407535357f4ddf16aa8f1f9a97bb1cbe6cdf
git branch -D -- 'worktree-agent-a38bf08560c27a579'
# expected f7430c407fff14638ca771107efeee3466a71c0a
git branch -D -- 'worktree-agent-a3ea3b1d38e084930'
# expected 572f5aa26d96e9fe75c1f643832ca824c827b921
git branch -D -- 'worktree-agent-a3f099488f9a82ed1'
# expected 7758a13c437c1267b261535e80e659a44835e87e
git branch -D -- 'worktree-agent-a3ff0ef740318af5e'
# expected 5ccffbe91fd4eb24601c7a677770824924976da0
git branch -D -- 'worktree-agent-a4ab94c51456abb78'
# expected 57bd316aa980e7f76d760e2439751046d027a0d8
git branch -D -- 'worktree-agent-a4b70cbf41800d5ca'
# expected a1c1c26bfb7196734e944a62dd9820992914131e
git branch -D -- 'worktree-agent-a4d512969948551d8'
# expected d6e867d2cf3e45b5748856abfa3f865f56fc4aba
git branch -D -- 'worktree-agent-a5287232297d9fc77'
# expected c198e61253f71c908462e267803425bb02f561f7
git branch -D -- 'worktree-agent-a52b467fa9f45f7da'
# expected 4f3b1fe63876ce664722131ff873a04ef759d30a
git branch -D -- 'worktree-agent-a5391ce09098b9c73'
# expected 715017882b6fbb79f3fd9f86bf97796ea3f02b24
git branch -D -- 'worktree-agent-a53fe1fe4f7a84b07'
# expected a3152d48b66c8f28b953cf6d46adfa96a071acc2
git branch -D -- 'worktree-agent-a54190da471e3ddf9'
# expected 2b8eccaf636217155f4cd94f3046d7cd5ee0d280
git branch -D -- 'worktree-agent-a556441520fcd3c9c'
# expected 87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5
git branch -D -- 'worktree-agent-a55e79db9100f2290'
# expected 87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5
git branch -D -- 'worktree-agent-a59705cabd6f6c62d'
# expected f5e8ae5f76af54b98c06dc7b52c3eeade6f6c3d0
git branch -D -- 'worktree-agent-a5a06a944cf8dedbd'
# expected ba78631e1562ddcf45ad6358ce047289bcd342ae
git branch -D -- 'worktree-agent-a5c128404456a4b8e'
# expected b5242ea33c47b90353a3adc4e554d4ed80a94746
git branch -D -- 'worktree-agent-a5c3d72a8892d8be8'
# expected 54e199ea22450e77563959de266ac79534bbc2dd
git branch -D -- 'worktree-agent-a5c985a3fe89fb27d'
# expected 87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5
git branch -D -- 'worktree-agent-a5cd4e9707c993055'
# expected 2e4ca17aae1421f2f032c616dd28a4fd8c32ecbd
git branch -D -- 'worktree-agent-a5dbf1a5a83fba809'
# expected eb9c1dee7029a301d4bda535f12b380b8f80ddbc
git branch -D -- 'worktree-agent-a60b48a57928d5895'
# expected 87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5
git branch -D -- 'worktree-agent-a6190fadbdb2acebe'
# expected 33636ec12a9a6ea02bb434a6b49097fae0dfe0a8
git branch -D -- 'worktree-agent-a670c42a14aa79fba'
# expected 93229e3d09baeb2a86059769c166a8220436a0f4
git branch -D -- 'worktree-agent-a6a9a0b3a6b20d104'
# expected c22e7311d2bc3a575077a69ac444ce24ffb640ab
git branch -D -- 'worktree-agent-a6f676d19f96310cd'
# expected 5ae45f2bb31cbef0a540ea106b9ee3343bfa8c37
git branch -D -- 'worktree-agent-a6ffa39f8ba6a8814'
# expected 332d9b551d449a48a98535d85dea25eb4a249fb5
git branch -D -- 'worktree-agent-a7071f4335335f4f5'
# expected 53bd19f696f7dfd3be01fef8aea248bba49c80d5
git branch -D -- 'worktree-agent-a717758e4fb09729a'
# expected 01962ce656c3f9f461bf259b0b67d5cca167a50f
git branch -D -- 'worktree-agent-a745688e80fa5caa9'
# expected f93c76af239ea37b36e63f7d3ed4190a38b04eaf
git branch -D -- 'worktree-agent-a75a01fb'
# expected 6577668859c6d97f2412eb2f856ec9dd4d01777b
git branch -D -- 'worktree-agent-a762a0a5e278cb792'
# expected 03e3e38c91039cb57f5703323a729c04a4ff2225
git branch -D -- 'worktree-agent-a77c43dcc4f3b0197'
# expected 6f2ac9566a99fc921f9cee022643e77e8c9ccf40
git branch -D -- 'worktree-agent-a781bda1e318a3477'
# expected 19ccf9e811782064d66eea65b070d88880cffb39
git branch -D -- 'worktree-agent-a795927256b2f29e7'
# expected bcbc46f2e5576b7f3e5e5868ae38b94fba3694e2
git branch -D -- 'worktree-agent-a7a973b4596ade6b1'
# expected 0a7f791abb96b79fc361ce5cd4fe10b621143595
git branch -D -- 'worktree-agent-a7bed877f805980b0'
# expected 0bc98ffc868e964aa212de0007e85cb683a8c4ed
git branch -D -- 'worktree-agent-a7e7c39e9775a0f73'
# expected affd0869a4bbaccc69b4dd8a0e574560ab0b856b
git branch -D -- 'worktree-agent-a7f0838e43f31b457'
# expected 87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5
git branch -D -- 'worktree-agent-a8194dbbf32434db9'
# expected a8898a7a7d9cc67f5cf3b81d451c64ed698a86cf
git branch -D -- 'worktree-agent-a8213859c9ad5c121'
# expected 4795a219030523cb83614b241548ee1ef0a7ec9d
git branch -D -- 'worktree-agent-a838fcfecbdc8645b'
# expected ab9368f81aa580a007cc49c91240754206d3e1ec
git branch -D -- 'worktree-agent-a840269e071c723d0'
# expected 19dc31b40529ef1c828ed8e52d6839aa817d2751
git branch -D -- 'worktree-agent-a874d90a1a9da98d0'
# expected 53bd19f696f7dfd3be01fef8aea248bba49c80d5
git branch -D -- 'worktree-agent-a8c67b5203e41c78e'
# expected 5b2dc5f8b3515cbe231bfe24d3fea22bf1cd17e8
git branch -D -- 'worktree-agent-a8e7a7cd54b0167e9'
# expected eb9c1dee7029a301d4bda535f12b380b8f80ddbc
git branch -D -- 'worktree-agent-a8f35b1a442cb2147'
# expected bcc54af21b97bc723890f9684fbff083b72cf441
git branch -D -- 'worktree-agent-a9064f78118fe3182'
# expected 4d7184aeaec8f2a768406b4872b4daede1228b17
git branch -D -- 'worktree-agent-a93ea1c02c0aa67a6'
# expected da09db224cc3ecdd9d3a23ae2cc405e56ee9cd67
git branch -D -- 'worktree-agent-a94f79872cf3c2956'
# expected 5ec0f6a4119ce23a0a4ce4790d839e173d2514d3
git branch -D -- 'worktree-agent-a9929996116eab11d'
# expected 53bd19f696f7dfd3be01fef8aea248bba49c80d5
git branch -D -- 'worktree-agent-a9a2270cdf24df420'
# expected fefe72fe5d6cd72e71b7fbc6b7f1ec0484f22821
git branch -D -- 'worktree-agent-a9b538e94beefb1bb'
# expected 9e7dfd4ca6a1b2f4608d38eebac4b6940919234b
git branch -D -- 'worktree-agent-a9e7150a335178db6'
# expected cce3895fcaafec47dd4a1c4dd9b8588fec9cedcb
git branch -D -- 'worktree-agent-aa22a939b267fbed4'
# expected 5b01e397a152e62b9b4d0101d05c989fc49d512d
git branch -D -- 'worktree-agent-aa44d177d8f47b9fc'
# expected 67b4a439fd59bca4080af1ac424d8928fe5f0c9c
git branch -D -- 'worktree-agent-aa51708f12ba44358'
# expected ab9368f81aa580a007cc49c91240754206d3e1ec
git branch -D -- 'worktree-agent-aa9087fcaaa04e2ac'
# expected 2e3f61f5096a9e53f172bbf886f0a8ca42054bed
git branch -D -- 'worktree-agent-aa9f436167ca0131a'
# expected c0e99ba4e324e9bee2bc3a8d8e9c1c8ea8029d69
git branch -D -- 'worktree-agent-aab1fb2eaf05f2174'
# expected fbad804ac30324c280313fcd593a10c6f256b19d
git branch -D -- 'worktree-agent-aac10f493d748fa5c'
# expected 3b785f9d4ec172e3f30bb16e5d445c358ca85b47
git branch -D -- 'worktree-agent-aacfbf4446690cbea'
# expected f93c76af239ea37b36e63f7d3ed4190a38b04eaf
git branch -D -- 'worktree-agent-ab0fb0a7'
# expected 22d3ad872bc71cd02fe16e3cd3b97c08b229d38a
git branch -D -- 'worktree-agent-ab1657e4739bfb5ad'
# expected 4a4b6718f8d69c692138a1fdc7e41b5abeb77c89
git branch -D -- 'worktree-agent-ab2f89d27bbf14bde'
# expected ed0c4539207ec34ef428cff45bfb7ee64490ec56
git branch -D -- 'worktree-agent-ab454ff44a5679193'
# expected 53bd19f696f7dfd3be01fef8aea248bba49c80d5
git branch -D -- 'worktree-agent-ab7db2284f1a23a25'
# expected d94988a86d635cbeaebfcbf11af4e97c2260d83b
git branch -D -- 'worktree-agent-ab82847f1df895787'
# expected 0d8d7bbed9b204704b4f9a02c996cc6a268b7472
git branch -D -- 'worktree-agent-abf2d752f509e445b'
# expected 0e997243358ea5db090a4fe44bbef9d7d7902e09
git branch -D -- 'worktree-agent-abf3b3a8687622967'
# expected f93c76af239ea37b36e63f7d3ed4190a38b04eaf
git branch -D -- 'worktree-agent-ac1556ef'
# expected 8b44a5db9893cb768102b316fa55e7a28166ef09
git branch -D -- 'worktree-agent-ac51ccfd88e45a7e0'
# expected fbd556116724e10726899e43a4d7d084f96f5669
git branch -D -- 'worktree-agent-ac625c4f4e8d21b0e'
# expected d89a4ad3b82cf194b62b15be7774b58482f252b2
git branch -D -- 'worktree-agent-ac67214a25c77896d'
# expected 18f84288d9ba126e46c834ab34ba9a000cb820ba
git branch -D -- 'worktree-agent-ac81596c5b45c68c9'
# expected d44200f23f9f4cd65633f3ff5407098d31c2b334
git branch -D -- 'worktree-agent-ac919199823a00f48'
# expected ea19d4b75cc9de1bf33d48d615678b8bd8356715
git branch -D -- 'worktree-agent-ac98e8e8cf1e59684'
# expected 0e6cffa966f4edbcd5ac49ac5b47ab7e0d91aa44
git branch -D -- 'worktree-agent-acc5272eb7eb24e4e'
# expected e1309beb8437bfb2b0e8a34446c86a86efc44e74
git branch -D -- 'worktree-agent-acce1e33b7aef0abe'
# expected f93c76af239ea37b36e63f7d3ed4190a38b04eaf
git branch -D -- 'worktree-agent-acfd5ca9'
# expected f65bab75adf3a949c82402a4f0c6767166bcb142
git branch -D -- 'worktree-agent-acfebfb1bbb7e02af'
# expected 0848edd907c3bf5bf0982e9bf28a651e11e88ea8
git branch -D -- 'worktree-agent-ad5be481f59c206d2'
# expected 0dd3b0e4d34dcea27e0568b74932c8a82e4babc6
git branch -D -- 'worktree-agent-ad81d6d15fc57b088'
# expected f93c76af239ea37b36e63f7d3ed4190a38b04eaf
git branch -D -- 'worktree-agent-ad8eb8ca'
# expected be56567ec52efe4a92647bfd0b2d200e78c251bb
git branch -D -- 'worktree-agent-adb355036fe847189'
# expected 16b1dcb3fe9b4d4e20bc18eb9fc4dfb2c9c20510
git branch -D -- 'worktree-agent-adec00ae3a2e7dccc'
# expected c5f6f9c4aa274acac261d7fd77fb82d6db3854cb
git branch -D -- 'worktree-agent-adfd16bf190678bcd'
# expected 66cd2eac050c02fd005a9b13e7d1b9cf072b6cea
git branch -D -- 'worktree-agent-ae06d26a381e039cc'
# expected e297ea860f72d91d1bb567943143834bb5ab5551
git branch -D -- 'worktree-agent-ae2f8898ea0b703a7'
# expected 87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5
git branch -D -- 'worktree-agent-ae3050bc4e4ca4e49'
# expected 52be577e7320b69116215b57505d3c076c2577c4
git branch -D -- 'worktree-agent-ae33eec5a00d24264'
# expected 618a3d18313b347c234b847eec3f5d780bf6a6dd
git branch -D -- 'worktree-agent-ae9d48bf5dc036db8'
# expected 69a8ff8e4a17f941f318f5cd9936a58090696e28
git branch -D -- 'worktree-agent-aece02885ca19e959'
# expected 87b8e44c2f295eaeef21680c858a7ddfa0b8dbf5
git branch -D -- 'worktree-agent-aecf5fa60c4ffcaea'
# expected db007c311a987c35d27b306ec051565fc8da79ab
git branch -D -- 'worktree-agent-aef0655458c9f55b9'
# expected 4ac6673690ad50408b78bcf3cc87ab3a635f05bd
git branch -D -- 'worktree-agent-af4b9c0445be5f5a5'
# expected 451d2ebd714033a3b1f6bba3fc1b939f9d086efb
git branch -D -- 'worktree-agent-af95ea98f982612d6'
# expected 676f96d1c4ccf4d75094d4a0dd2d015a3e1b58d0
git branch -D -- 'worktree-agent-afa591a17c448320e'
# expected e5df03e6b8e3754a3c6f8a62dc4797b5b9773a21
git branch -D -- 'worktree-agent-afa6d1c4926e46d77'
# expected e98560a698804aaacbbe07fbf2bd4d86bb1aeb9f
git branch -D -- 'worktree-agent-afae520a937d45e74'
# expected 087e877f6aaa2688ac2b41a96d970ee5b2ec27b1
git branch -D -- 'agent-16-league-switcher'
# expected 739b8da416bb5930f5b467a8f9b449397c9a47f6
git branch -D -- 'chore/breaker-calibration-boundary-pin'
# expected 76c24247004c39afc0ee84747056e8b3d2edf393
git branch -D -- 'chore/breaker-sweep-ledger'
# expected e00940d8c4ce36be2d082f985c76c99bb2c49e11
git branch -D -- 'chore/commit-docs-and-claude-tree'
# expected 8353ec3075826d6db89efbf4231e86d137450959
git branch -D -- 'chore/eas-submit-ascappid'
# expected b8c8dd598e5d5302b240a4fc3e78b9265bd76ede
git branch -D -- 'claude/api-audit-redundancies-9a6075'
# expected 4f8c05073a1fc2b5bbb1bdd02dab89f7e8cfee4d
git branch -D -- 'claude/app-entry-platform-options-3e16ac'
# expected 0a924974a990b96ec7ba98d8a1bfa45ddb430c1d
git branch -D -- 'claude/busy-cohen-7530c5'
# expected 0a924974a990b96ec7ba98d8a1bfa45ddb430c1d
git branch -D -- 'claude/busy-hodgkin-b23fda'
# expected ad96131861d96a7486a941227781baecc1b10453
git branch -D -- 'claude/ci-gotchas'
# expected bec25bbf1f08e9a1083a448e4c2a4892e55239cb
git branch -D -- 'claude/compressed-board-ship-record'
# expected c265a8af0779b40486b04e9c16a3d3239bc8c748
git branch -D -- 'claude/counterparty-breaker-plan'
# expected 55f06384ed5e944b4e61fe1b8ce23057f9d952a7
git branch -D -- 'claude/entry-platform-login-option'
# expected 3f5af51c3e496c48a958171425933177cf9f9691
git branch -D -- 'claude/finder-gap-analysis-writeback'
# expected a12ca6809add360e7e54a335b415cbd30024735a
git branch -D -- 'claude/iap-enablement-writeback'
# expected 0a924974a990b96ec7ba98d8a1bfa45ddb430c1d
git branch -D -- 'claude/jolly-khorana-945330'
# expected 491427a631711958692c07785fca86ddcf1105da
git branch -D -- 'claude/monthly-trial-3d'
# expected f7833d566f9fddf1c320e7f217a843ce7435a1e0
git branch -D -- 'claude/new-user-feedback-55320e'
# expected a08019768e39539d0eccdc03125bdfcfe7d71016
git branch -D -- 'claude/platform-entry-decouple-apple'
# expected f7885524c22e648c9941061c58ebb665dd2623fc
git branch -D -- 'claude/propose-label-writeback'
# expected 5189a14e07fef703c1eb029f5472d5a26e3e85f5
git branch -D -- 'claude/q034-sku-ruling'
# expected 832d9ca1e34f3808ecebef3c3ceb7a1910e626e4
git branch -D -- 'claude/q035-q036-operator-answers'
# expected a9b86950dad2975976f383cd1fa8beb242425f02
git branch -D -- 'claude/ram-mascot-fleeced'
# expected 31f757297d5d40ac5a2bcdf1171e7468391e9a77
git branch -D -- 'claude/sentry-wizard'
# expected bf92d4eea6e211305589636ee2a61a218fca4f42
git branch -D -- 'claude/tip-jar'
# expected 32d95767dd6a16acccae07669a50f7884371d4cb
git branch -D -- 'claude/trade-model-restrictiveness-7f3975'
# expected 6ac1e8a36c7a058e156b4a632e2e05fcb704fd5b
git branch -D -- 'claude/trade-suggestions-review-69c9eb'
# expected 0bad37ca8b5672629339a15e0d70caf8a7bb9160
git branch -D -- 'claude/trial-lengths-v2'
# expected 71f63da347d72d3cec95192a6a4dbf66166ac2c9
git branch -D -- 'claude/vigilant-spence-8583f5'
# expected b59951c984db0318946e11c798b67788ff929f0a
git branch -D -- 'docs/feedback-batch-2-prds'
# expected 80bb318c0b6e31db48f155edd1eaca4cbb8e3412
git branch -D -- 'docs/null-dwell-writeback'
# expected cf5ef852c6771a7a04242abe4c1aa970ba1256b4
git branch -D -- 'docs/qa-reports-feedback-wave-0824'
# expected 1d49d5fc8a8fcad4291becf9eb412e48533978e3
git branch -D -- 'feat/bakeoff-composition'
# expected 6d60d955cf432bf09c98798a6a8f7329b398b0da
git branch -D -- 'feat/celeb-once-and-copy-tiers'
# expected 4a8722959d4c20ab7a324292eff4e3042de0727b
git branch -D -- 'feat/datetime-utcnow-cleanup'
# expected fa9979bda197ca601b919f938fec55d2fd9a6314
git branch -D -- 'feat/fb-07-trios-cleanup'
# expected 8eabe6c3d111b83fe97fdbe9a20e4bb42356fa4e
git branch -D -- 'feat/feedback-admin-list'
# expected 1d3ffca88de44f41a62e45bf3d3d43437d018785
git branch -D -- 'feat/feedback-batch-4-polish'
# expected f4b3bfb5eb45b95ffc19da8724f1ea3fd80c43d8
git branch -D -- 'feat/guided-onboarding-platform-aware'
# expected 2cb2ce792269736d2f41817c54eac77031170334
git branch -D -- 'feat/init10-player-view-param'
# expected 482b07dd9b86438c20e4593570fd8eeb87d07273
git branch -D -- 'feat/jon-360-362'
# expected b1a5024a6ef238d2b9fb30606c25548e2f386bae
git branch -D -- 'feat/league-pick-value-alignment'
# expected 087e877f6aaa2688ac2b41a96d970ee5b2ec27b1
git branch -D -- 'feat/notifications-clear-button'
# expected 21ad574b9871e0837a9e9ef6fa6cbc5c92818966
git branch -D -- 'feat/receipts'
# expected 95709751e22c7ac3f08bc131c4adb57361ff53a8
git branch -D -- 'feat/slot-pricing-unconditional'
# expected 692e6fe4b863cd370929e6244b2fba52e2663254
git branch -D -- 'feat/tier-config-and-bench-fixes'
# expected c92141b386a0039510fda80b37005256c9d3b428
git branch -D -- 'feat/tiers-multiselect'
# expected f248197bbd348fd6790506c51fc6d474c7acb1a5
git branch -D -- 'feat/wave1-perf-code'
# expected 8c2b5ec37c42e4aded02dfd7bb06bd6fd7fc4575
git branch -D -- 'feat/wave2-init08-client'
# expected bec210780d0049e28c9f91c6f1c3cb4e3688c927
git branch -D -- 'feat/wave2-init09-trade-prune'
# expected 040188162b92af41f980d1694d47f69ca0f0ab8c
git branch -D -- 'feat/wave2-init11a-13'
# expected 20bebe4ceb3065752f954c24d97b259a0bffe158
git branch -D -- 'feat/wave2-init12b'
# expected cd1248c2b314c536e119c3b130e4b1157bd7f9cf
git branch -D -- 'feat/wave2-init14b-db-hygiene'
# expected a75ba55a6cf00d6f8a9714764e980f913bceb2f5
git branch -D -- 'feat/wave2-init15-docs'
# expected a8e5ef81597b1fc0dd09449a39668eeb5f6bf4d8
git branch -D -- 'fix/384-tour-device-feedback'
# expected 4df39bef29971e01bc05882b5f069eccd50f74bd
git branch -D -- 'fix/copy-tiers-include-seed-only-players'
# expected 973ad489cda2b18880fb623eab269bd7bff921e9
git branch -D -- 'fix/feedback-qc-trio-throttle'
# expected cacde8af44ab65befae2b3941ccb777d617915a3
git branch -D -- 'fix/feedback-rehydrate-unsynced'
# expected c693581795c7b62138a348d4b60d0c4d9003b247
git branch -D -- 'fix/feedback-tiers-ux'
# expected 317e42969a449c3ec34920d9e8540f65eed24114
git branch -D -- 'fix/feedback-trade-match-100'
# expected cdeb130914e8f72916216764910caaeaf77ab1ab
git branch -D -- 'fix/feedback-trios-polish'
# expected ccb08e21bfc0e9b0c845a99bcf3e36f8eb74b4d3
git branch -D -- 'fix/guide-band-entry-animation'
# expected 3e80e8af408a250d56668a99208840af40349a7e
git branch -D -- 'fix/lift-top80-cap'
# expected 087e877f6aaa2688ac2b41a96d970ee5b2ec27b1
git branch -D -- 'fix/manual-rankings-remove-kebab-column'
# expected 5e52cdac886deae8fa12fa4a314ddb72d28bd8de
git branch -D -- 'fix/mobile-warm-player-cache-on-init'
# expected 7fe1e9b61eb1685e2709c918c34cc79ce460f947
git branch -D -- 'fix/package-benchmark-sweetener'
# expected 7b9df5db0327e8a86c7319282579407c2749cddf
git branch -D -- 'fix/pick-assignment-missing-user-team'
# expected a726995d872952d0425f7098ae69405b47bd07f1
git branch -D -- 'fix/preserve-tier-overrides'
# expected 2dd277e77f0b6f2d54a4be17c5a2b0d737fade18
git branch -D -- 'fix/rankings-progress-monotonic-unlock'
# expected 087e877f6aaa2688ac2b41a96d970ee5b2ec27b1
git branch -D -- 'fix/remove-trios-info-icon'
# expected 8c3a5550b63a53f27af467bbfac280266f41df76
git branch -D -- 'fix/review-batch-backend-perf'
# expected 9d99ab81efec8e35f3a1f5aa08f3a931b850f325
git branch -D -- 'fix/review-cache-and-mutations'
# expected 78b1568fa9275544bb2b32220b169816d208825d
git branch -D -- 'fix/review-flags-and-notifications'
# expected 5e1a5a879b6cad551b4e0d38f35c51dddd47fef4
git branch -D -- 'fix/session-init-parallelization'
# expected be9afbd4482fbd432bb2c283bf778d2eafa970a5
git branch -D -- 'fix/test-user-logins'
# expected 34b8d4c3eeaf835efd4bcae94721cf30ae126965
git branch -D -- 'fix/test-user-logins-tev2'
# expected 1b4a9a4ce866d8cd7f5c72badd14cf8da0e2099a
git branch -D -- 'fix/tier-arrows-edge-detection'
# expected 97a29130fa31cd5c861d5f0acc299eadc4d2fa36
git branch -D -- 'fix/tier-overrides-survive-swipes'
# expected ee8c48b5ca0db2d80a9ae0d0f61cb34b709a03f1
git branch -D -- 'fix/tiers-drag-worklet-crash'
# expected 0a924974a990b96ec7ba98d8a1bfa45ddb430c1d
git branch -D -- 'fix/tiers-drop-coord-space'
# expected b68c193de946f389a778fe151b566202d788c385
git branch -D -- 'fix/tiers-format-sync'
# expected ad8471b51f6d92b6c35871c42055061dbd2d32c9
git branch -D -- 'fix/tiers-multiselect'
# expected 6a5a08d92decd7524e561bb0b6ff97c55db5ba1e
git branch -D -- 'fix/trade-job-fmt-undefined'
# expected 087e877f6aaa2688ac2b41a96d970ee5b2ec27b1
git branch -D -- 'fix/trios-remove-college-2026-04-26'
# expected e5fc5cf6887172e04d58da3c5a215d739821756d
git branch -D -- 'fix/web-trades-snapshot-poller'
# expected f949fec2639dc509d92af217d5c84be52ea76f75
git branch -D -- 'living-memory-revival'
# expected 087e877f6aaa2688ac2b41a96d970ee5b2ec27b1
git branch -D -- 'mobile/independent-followups'
# expected 2a5ca54a518b60de307988ea153851295823c4aa
git branch -D -- 'mobile/session-expired-recovery'
# expected a834d383d68ff0a945bda7cb0803cf7e2342f904
git branch -D -- 'mobile/tiers-persistence-parity'
# expected f5446bbade03074b88d0c5f5a3adcad78b8a3e02
git branch -D -- 'mobile/web-parity-2026-04-29'
# expected dc83ce41ff684f396c3ad05c1791e334aa96cad2
git branch -D -- 'perf/find-a-trade-faster-pregen'
# expected b5f1f39eafdfb786d1f811d42305fedabf36869e
git branch -D -- 'perf/find-a-trade-tighter-cap'
# expected 9a3475dfae187d8c7de27170a17de9c651b3e086
git branch -D -- 'perf/league-matches-progressive-paint'
# expected b12488d25c2454b461d4b830d0ed79415d08fed0
git branch -D -- 'perf/trade-tier-priority'
# expected dd8f95b0d2d5d433ac42c3492c549a1a0eab3163
git branch -D -- 'perf/trios-fast-load'
# expected 0eca3c4e003a90578a3ed6f0e3a4bc64f478bd05
git branch -D -- 'perf/warm-endpoint-and-boot-ping'
# expected 557260400630dc6fac14161a7cf1d5c37967e3cf
git branch -D -- 'plan/receipts'
# expected 8dca63c33b1a1ae6a7ce3a35fd25b5335c923c9a
git branch -D -- 'recovery/ledger-entry-login-option'
# expected 81001c272140fdd41277bdbc71cfa0a886888036
git branch -D -- 'recovery/ledger-landing-platform-options'
# expected 141546aec74a4845d7567ba4149bd0445b99f091
git branch -D -- 'recovery/ledger-platform-entry-decouple'
# expected 20b1d22a7d8db1b8d9fb1c4753174a834b140a28
git branch -D -- 'recovery/ledger-v1168-sweep'
# expected 364d8d7cdd97d90793f273f6411f134d77fbf3f7
git branch -D -- 'release/v1.16.8'
# expected 96e48ed7a0809c86c2653c83d74613c07d203e67
git branch -D -- 'release/v1.16.8-record'
# expected be9237b23e0f42aaf41a8a69cd5a0441824dfc38
git branch -D -- 'research/ktc-pick-comparison'
# expected 45406790e073c10457978e0dc2c3e29913ecd08d
git branch -D -- 'ship/armc-sweetener'
# expected 6a152bf52b72d13f91e6a89ee2d69f1f92696f74
git branch -D -- 'web/tiers-within-tier-reorder'
# expected 1c04bc3ab3b072604400bc1425a193ff4f5b2172
git branch -D -- 'worktree-agent-a1666e74f3763e0a7'
# expected 6da7747089ba1c8a77a8dd0232e2ef985bceebfc
git branch -D -- 'worktree-agent-a23ba874f1881182e'
# expected b2127cee5d425cd6cda9806732d604cc91be1557
git branch -D -- 'worktree-agent-a3f23e0d54808496f'
# expected 7633561ec801e9a521e65ebb30dd22bb6f02f532
git branch -D -- 'worktree-agent-adc544906c182a442'
# expected 2d6d4f7940f751481f336e473b1e7e3278b8fa4d
git branch -D -- 'worktree-agent-aec3f38caa8be282f'
```

The queue worktree/branch target was separately captured and completed:

```sh
# tip dc781ff5495f35f06ce5f5214f25f941fb188c50; only untracked node_modules symlink inspected
git worktree remove --force '/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/agent-ae3050bc4e4ca4e49'
git branch -D -- 'feat/mobile-b5-trade-queue'
# Recovery retained by parent:
git branch 'feat/mobile-b5-trade-queue' refs/recovery/2026-09-04/mobile-b5-trade-queue
```

Remote deletion manifest: all 76 candidates below are separate from local deletion, have no open PR at inspection, and are not current worktree owner names. Each push uses an expected-tip lease so a newly advanced remote branch is not deleted. The executor must still reread active/open-PR state and the pre-deletion ledger.

```sh
git push origin --force-with-lease=refs/heads/analytics-300:0b6487163b14990af330612a6b1818ca31da6d2d :refs/heads/analytics-300
git push origin --force-with-lease=refs/heads/chore/commit-docs-and-claude-tree:e00940d8c4ce36be2d082f985c76c99bb2c49e11 :refs/heads/chore/commit-docs-and-claude-tree
git push origin --force-with-lease=refs/heads/chore/eas-submit-ascappid:8353ec3075826d6db89efbf4231e86d137450959 :refs/heads/chore/eas-submit-ascappid
git push origin --force-with-lease=refs/heads/chore/session-wrapup:4340b60473bc1ab6d39fd80f3d312ad4a6e8c778 :refs/heads/chore/session-wrapup
git push origin --force-with-lease=refs/heads/claude/api-audit-redundancies-9a6075:b8c8dd598e5d5302b240a4fc3e78b9265bd76ede :refs/heads/claude/api-audit-redundancies-9a6075
git push origin --force-with-lease=refs/heads/claude/busy-swartz-521ff5:18f15f7ad36ca988ef364fc4d0041218f7313a52 :refs/heads/claude/busy-swartz-521ff5
git push origin --force-with-lease=refs/heads/claude/finder-gap-analysis-writeback:3f5af51c3e496c48a958171425933177cf9f9691 :refs/heads/claude/finder-gap-analysis-writeback
git push origin --force-with-lease=refs/heads/claude/ftf-file-continuation-c9185e:5adc848474f4b766101f2f1d56127577d066ab88 :refs/heads/claude/ftf-file-continuation-c9185e
git push origin --force-with-lease=refs/heads/claude/new-user-feedback-55320e:f7833d566f9fddf1c320e7f217a843ce7435a1e0 :refs/heads/claude/new-user-feedback-55320e
git push origin --force-with-lease=refs/heads/claude/new-user-feedback-d4c47d:62bd658f65639772a8ca70f92bb74f769b1f2389 :refs/heads/claude/new-user-feedback-d4c47d
git push origin --force-with-lease=refs/heads/claude/propose-label-writeback:f7885524c22e648c9941061c58ebb665dd2623fc :refs/heads/claude/propose-label-writeback
git push origin --force-with-lease=refs/heads/claude/q035-q036-operator-answers:832d9ca1e34f3808ecebef3c3ceb7a1910e626e4 :refs/heads/claude/q035-q036-operator-answers
git push origin --force-with-lease=refs/heads/claude/ram-mascot-fleeced:a9b86950dad2975976f383cd1fa8beb242425f02 :refs/heads/claude/ram-mascot-fleeced
git push origin --force-with-lease=refs/heads/claude/team-outlook-experience-27a7a1:b3f7d92bd20a68cd7af9eb36da0d463a69326b9a :refs/heads/claude/team-outlook-experience-27a7a1
git push origin --force-with-lease=refs/heads/closeout-mock-draft:aaa98449d4fdcb4c2c351018f03b1a7613c7dc88 :refs/heads/closeout-mock-draft
git push origin --force-with-lease=refs/heads/closeout-wave:68e0b4dfc6ca28bc52d0279344f7e805e283f112 :refs/heads/closeout-wave
git push origin --force-with-lease=refs/heads/context-slim-2026-08-08:4a381f7eefd535a02018f0b2c7587175c66d9f0f :refs/heads/context-slim-2026-08-08
git push origin --force-with-lease=refs/heads/docs-297-302-artifacts:7f7524c3822d4feaf3e86223cc204626d3961a2b :refs/heads/docs-297-302-artifacts
git push origin --force-with-lease=refs/heads/docs/feedback-batch-2-prds:b59951c984db0318946e11c798b67788ff929f0a :refs/heads/docs/feedback-batch-2-prds
git push origin --force-with-lease=refs/heads/docs/navdoc-refresh-2026-08-18:38a989c88b054ac2d90f443e4866a4faa10f96a3 :refs/heads/docs/navdoc-refresh-2026-08-18
git push origin --force-with-lease=refs/heads/docs/null-dwell-writeback:80bb318c0b6e31db48f155edd1eaca4cbb8e3412 :refs/heads/docs/null-dwell-writeback
git push origin --force-with-lease=refs/heads/feat/datetime-utcnow-cleanup:4a8722959d4c20ab7a324292eff4e3042de0727b :refs/heads/feat/datetime-utcnow-cleanup
git push origin --force-with-lease=refs/heads/feat/espn-credential-verify:2fa1ff24f0ceb143d7b23b79ed5ea874a218a619 :refs/heads/feat/espn-credential-verify
git push origin --force-with-lease=refs/heads/feat/fb-07-trios-cleanup:fa9979bda197ca601b919f938fec55d2fd9a6314 :refs/heads/feat/fb-07-trios-cleanup
git push origin --force-with-lease=refs/heads/feat/feedback-admin-list:8eabe6c3d111b83fe97fdbe9a20e4bb42356fa4e :refs/heads/feat/feedback-admin-list
git push origin --force-with-lease=refs/heads/feat/feedback-batch-4-polish:1d3ffca88de44f41a62e45bf3d3d43437d018785 :refs/heads/feat/feedback-batch-4-polish
git push origin --force-with-lease=refs/heads/feat/feedback-liked-trades-waiting:8026b7fbc32c3c2a7ddd69aa7585eaf20d94979f :refs/heads/feat/feedback-liked-trades-waiting
git push origin --force-with-lease=refs/heads/feat/init10-player-view-param:2cb2ce792269736d2f41817c54eac77031170334 :refs/heads/feat/init10-player-view-param
git push origin --force-with-lease=refs/heads/feat/jon-360-362:482b07dd9b86438c20e4593570fd8eeb87d07273 :refs/heads/feat/jon-360-362
git push origin --force-with-lease=refs/heads/feat/light-tier-flags:a362a15ad810b579d73940ffa0a485d1ec55ce86 :refs/heads/feat/light-tier-flags
git push origin --force-with-lease=refs/heads/feat/mfl-send-integrated:3af201ac7ddd3f18c58fe0f6d7c7fd39c9ccfd4e :refs/heads/feat/mfl-send-integrated
git push origin --force-with-lease=refs/heads/feat/send-auth-lazy:7315d8c62ec30ad47f2a27fdc7d6cbf5ef84aa05 :refs/heads/feat/send-auth-lazy
git push origin --force-with-lease=refs/heads/feat/send-in-espn:f89d8805c4ebd436705f5d59da1edc4fa9c2c82f :refs/heads/feat/send-in-espn
git push origin --force-with-lease=refs/heads/feat/sleeper-reachability-probe:1f349bd3cbb7742ff3e4301e77e8e7c296eff72d :refs/heads/feat/sleeper-reachability-probe
git push origin --force-with-lease=refs/heads/feat/team-review-batch-2:f56216e5931d336051648b889c23700ce74a1398 :refs/heads/feat/team-review-batch-2
git push origin --force-with-lease=refs/heads/feat/wave1-perf-code:f248197bbd348fd6790506c51fc6d474c7acb1a5 :refs/heads/feat/wave1-perf-code
git push origin --force-with-lease=refs/heads/feat/wave2-init07:241f2232fc4030e410a902433d69de43fb6ff792 :refs/heads/feat/wave2-init07
git push origin --force-with-lease=refs/heads/feat/wave2-init08-client:8c2b5ec37c42e4aded02dfd7bb06bd6fd7fc4575 :refs/heads/feat/wave2-init08-client
git push origin --force-with-lease=refs/heads/feat/wave2-init09-trade-prune:bec210780d0049e28c9f91c6f1c3cb4e3688c927 :refs/heads/feat/wave2-init09-trade-prune
git push origin --force-with-lease=refs/heads/feat/wave2-init11a-13:040188162b92af41f980d1694d47f69ca0f0ab8c :refs/heads/feat/wave2-init11a-13
git push origin --force-with-lease=refs/heads/feat/wave2-init12b:20bebe4ceb3065752f954c24d97b259a0bffe158 :refs/heads/feat/wave2-init12b
git push origin --force-with-lease=refs/heads/feat/wave2-init14b-db-hygiene:cd1248c2b314c536e119c3b130e4b1157bd7f9cf :refs/heads/feat/wave2-init14b-db-hygiene
git push origin --force-with-lease=refs/heads/feat/wave2-init15-docs:a75ba55a6cf00d6f8a9714764e980f913bceb2f5 :refs/heads/feat/wave2-init15-docs
git push origin --force-with-lease=refs/heads/feat/window-composite:bbc2e4b166925c4417bb5ec559a9241354b1b9fb :refs/heads/feat/window-composite
git push origin --force-with-lease=refs/heads/feedback-289-294:660004c13c74e18d3ef2054e87bb925091c97cd1 :refs/heads/feedback-289-294
git push origin --force-with-lease=refs/heads/feedback-integration-v2:8cbedf8c6927d0f1413146b2e7a3d4b248ef1174 :refs/heads/feedback-integration-v2
git push origin --force-with-lease=refs/heads/fix-easignore-screens:978910a4741dc511358931c5de337ec35aea9497 :refs/heads/fix-easignore-screens
git push origin --force-with-lease=refs/heads/fix/feedback-qc-trio-throttle:973ad489cda2b18880fb623eab269bd7bff921e9 :refs/heads/fix/feedback-qc-trio-throttle
git push origin --force-with-lease=refs/heads/fix/feedback-rehydrate-unsynced:cacde8af44ab65befae2b3941ccb777d617915a3 :refs/heads/fix/feedback-rehydrate-unsynced
git push origin --force-with-lease=refs/heads/fix/feedback-tiers-ux:c693581795c7b62138a348d4b60d0c4d9003b247 :refs/heads/fix/feedback-tiers-ux
git push origin --force-with-lease=refs/heads/fix/feedback-trade-match-100:317e42969a449c3ec34920d9e8540f65eed24114 :refs/heads/fix/feedback-trade-match-100
git push origin --force-with-lease=refs/heads/fix/feedback-trios-polish:cdeb130914e8f72916216764910caaeaf77ab1ab :refs/heads/fix/feedback-trios-polish
git push origin --force-with-lease=refs/heads/fix/finder-conditions-and-partners-copy:bda0d51844b289dc509f84c71c8a44a15f742fac :refs/heads/fix/finder-conditions-and-partners-copy
git push origin --force-with-lease=refs/heads/fix/pick-assignment-missing-user-team-clean:fc260dea52f39590f4e8b3ac100e83a0d4a5c424 :refs/heads/fix/pick-assignment-missing-user-team-clean
git push origin --force-with-lease=refs/heads/fix/review-batch-backend-perf:8c3a5550b63a53f27af467bbfac280266f41df76 :refs/heads/fix/review-batch-backend-perf
git push origin --force-with-lease=refs/heads/fix/review-cache-and-mutations:9d99ab81efec8e35f3a1f5aa08f3a931b850f325 :refs/heads/fix/review-cache-and-mutations
git push origin --force-with-lease=refs/heads/fix/review-flags-and-notifications:78b1568fa9275544bb2b32220b169816d208825d :refs/heads/fix/review-flags-and-notifications
git push origin --force-with-lease=refs/heads/fix/session-init-parallelization:5e1a5a879b6cad551b4e0d38f35c51dddd47fef4 :refs/heads/fix/session-init-parallelization
git push origin --force-with-lease=refs/heads/fix/test-user-logins:be9afbd4482fbd432bb2c283bf778d2eafa970a5 :refs/heads/fix/test-user-logins
git push origin --force-with-lease=refs/heads/fix/test-user-logins-tev2:34b8d4c3eeaf835efd4bcae94721cf30ae126965 :refs/heads/fix/test-user-logins-tev2
git push origin --force-with-lease=refs/heads/fix/tiers-drag-worklet-crash:ee8c48b5ca0db2d80a9ae0d0f61cb34b709a03f1 :refs/heads/fix/tiers-drag-worklet-crash
git push origin --force-with-lease=refs/heads/fix/tiers-drop-coord-space:0a924974a990b96ec7ba98d8a1bfa45ddb430c1d :refs/heads/fix/tiers-drop-coord-space
git push origin --force-with-lease=refs/heads/fix/tiers-multiselect:ad8471b51f6d92b6c35871c42055061dbd2d32c9 :refs/heads/fix/tiers-multiselect
git push origin --force-with-lease=refs/heads/living-memory-2026-08-10:3f073a57543b0cb1b76319d80aca6040fa02bd2c :refs/heads/living-memory-2026-08-10
git push origin --force-with-lease=refs/heads/living-memory-revival:f949fec2639dc509d92af217d5c84be52ea76f75 :refs/heads/living-memory-revival
git push origin --force-with-lease=refs/heads/mobile-version-1.12.0:c65493dec2b847ef08ad0a7f08bf8217ed90630c :refs/heads/mobile-version-1.12.0
git push origin --force-with-lease=refs/heads/mock-draft-fix:258940ff7a41b8c3fca9f56eb3e7f393a77993ce :refs/heads/mock-draft-fix
git push origin --force-with-lease=refs/heads/perf/league-matches-progressive-paint:9a3475dfae187d8c7de27170a17de9c651b3e086 :refs/heads/perf/league-matches-progressive-paint
git push origin --force-with-lease=refs/heads/perf/trade-tier-priority:b12488d25c2454b461d4b830d0ed79415d08fed0 :refs/heads/perf/trade-tier-priority
git push origin --force-with-lease=refs/heads/perf/trios-fast-load:dd8f95b0d2d5d433ac42c3492c549a1a0eab3163 :refs/heads/perf/trios-fast-load
git push origin --force-with-lease=refs/heads/perf/warm-endpoint-and-boot-ping:0eca3c4e003a90578a3ed6f0e3a4bc64f478bd05 :refs/heads/perf/warm-endpoint-and-boot-ping
git push origin --force-with-lease=refs/heads/screen-library-2026-08-09:dc91a91bd4a88e08f5a9c4e907e698fded436785 :refs/heads/screen-library-2026-08-09
git push origin --force-with-lease=refs/heads/session-closeout-2026-08-12:bc5521f713a05feecbd230027ce183e8330f877f :refs/heads/session-closeout-2026-08-12
git push origin --force-with-lease=refs/heads/teardown-remediation:2c10f4cc22bdb8dda49957ac7b6e92c76bee99a8 :refs/heads/teardown-remediation
git push origin --force-with-lease=refs/heads/trade-engine-v2:ca2b26aad6c695a662895fee8c5108fd291af200 :refs/heads/trade-engine-v2
git push origin --force-with-lease=refs/heads/wave-integration:11e468bb852404c7e26a88b3acea60b05f7b5ca8 :refs/heads/wave-integration
```

Recovery for each remote deletion: `git branch <name> <recorded-sha>`, then (only if restoring the remote is desired) `git push origin <name>:refs/heads/<name>`. A retained recovery ref/bundle is required for reliable recovery after reflog expiry; do not run aggressive garbage collection as part of cleanup.

## Execution status handoff

Parent-reported completed: **366 local branch deletions** (254 history-retained + 111 stricter-content-verified + queue), leaving **84 local branches**; **one queue worktree deletion**; **two missing registrations pruned** with their feature branches retained. Batch 4's results are durable in `docs/recovery/2026-09-04-branch-cleanup-batch4-result.json`. The audit agent did not perform any of these mutations.

Remote execution completed after the user confirmed both stored GitHub accounts were available. The initial read-only-account attempt deleted nothing. The successful retry used existing repository-admin account `mattmurf77` only within that process; the global default remains `meghanmurphyenglund`. All 76 candidates passed fresh live-tip, open-PR, worktree and content checks and were deleted atomically with expected-SHA leases. Post-deletion verification found all 76 target heads absent, all 76 original recovery refs intact, all 11 open PR heads preserved, and 22 origin heads remaining. See the [exact remote completion receipt](../../recovery/2026-09-04-branch-cleanup-batch5-result.json) and [dated recovery ledger](../../recovery/2026-09-04-branch-cleanup.md). Do not rerun the completed deletion batch.

After the first completed batch and concurrent security worktree creation, the fresh worktree snapshot counted **22 registered worktrees**. The initial 24 minus one queue worktree minus two missing registrations plus one security worktree equals 22. All remaining dirty worktrees, local data/credentials, main/current branches, open-PR branches, and unresolved branches are held.
