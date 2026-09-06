# Feedback 419–421 release worktree recovery

2026-09-06. **Captured before removal.** Scope is only temporary trees created for this batch under `/private/tmp/ftf-feedback-419-421-f1uMyt/`. The original dirty project checkout, unrelated trees/branches, private research/scripts, external scratch databases and archive inspections are preserved.

Release [PR #283](https://github.com/mattmurf77/fantasy-trade-finder/pull/283) head `d97459dc9f72ebe158f70fcbb86f29051659c206` squash-merged as `988fa2d690dfa9188f43c33e87dff9d60a5fabaa`. Root fetched and compared complete trees: identical. Exact-head CI passed all four jobs; iOS1.17.1(149) build completed from `d97459dc`. [Release and verification evidence](../feedback/items/419-rejected-interest-resurfacing/release.md).

## Captured targets

Paths below append to the exact temporary parent above. **Initial state: planned cleanup, not yet removed.** Each linked tree was clean, including all non-ignored untracked files, at independent inventory and is rechecked immediately before removal. No `--force` worktree removal is authorized by this record.

| Tip SHA | Branch / detached state | Directory suffix |
|---|---|---|
| `8f27421d59e7849e65244f2cd2964d9c504b72c1` | `codex/feedback-419-trade-disposition-20260906` | `trade` |
| `6838fe0fd009802e2738f3c082783e219f28375b` | `codex/feedback-419-mobile-20260906` | `mobile-419` |
| `a194efd7e798372140db36a1056c4b1e20345de7` | `codex/simple-player-presentment-20260906` | `packages` |
| `ff205431ab4cc709abd6a56dbfee6a90ecaae7df` | `codex/feedback-420-421-win-now-20260906` | `win-now` |
| `cf8cc2cc4d640581dd59bc78b2f36d19aff20846` | detached baseline | `419-provenance-baseline` |
| `741710c188a27e3e43b25e0b77372c5358617e72` | detached baseline | `packages-baseline` |
| `fe0f3cb1b3196ccb3de35da620f268b14e0f6264` | detached QA-A round1 | `qa-a` |
| `21e194a32fb1005112625d49dbdb12fca48ba09d` | detached QA-B round1 | `qa-b` |
| `293a41185c947519310eed582ba5b7a44e944dfb` | detached QA-A round2 | `qa-round2-a` |
| `dc2d949df8083a8ad8f9da3e543914c3214ebbc4` | detached QA-B round2 | `qa-round2-b` |
| `d97459dc9f72ebe158f70fcbb86f29051659c206` | `codex/feedback-419-421-20260906` | no longer checked out; integration now uses evidence branch |
| `d97459dc9f72ebe158f70fcbb86f29051659c206` | detached release/build source | `release-source` |
| `988fa2d690dfa9188f43c33e87dff9d60a5fabaa` | planned final detached cleanup target, after evidence merge | `integration` |

Keep detached `release-source` at `d97459dc` until exact-build submission/source verification is complete. Keep `integration`, now `codex/feedback-419-421-release-evidence-20260906`, until its documentation PR is merged and content verified. Capture those final tips before any later removal.

**17:40 UTC retention condition satisfied for release-source:** root verified exact submission FINISHED/error:null following completed build149/source verification. The explicit full tip above is now eligible for ordinary removal after another clean-state check. The published batch branch may be removed locally/remotely only if its exact tip still equals the captured `d97459dc`; PR #283 retains the published head.

**Final integration cleanup plan, not yet executed:** after this evidence branch passes CI, merges and has complete-tree equality with fetched main, keep the final evidence branch as a named recovery reference. Detach the clean integration tree to the already captured runtime merge `988fa2d6`, verify exact path/tip/clean state again, and remove it normally. No documentation is discarded: the complete evidence tree remains on main and the retained reference. This avoids trying to embed a commit's own SHA in its contents. Do not execute while the evidence tree is dirty or unmerged.

## Content preservation proof

- All four builder tips are contained in the reviewed release history. Independently checked mobile-419 and Win Now owned runtime files are byte-identical to release. Package helper/tests/service are identical; its specification matured in reviewed integration. Trade's remaining database/server differences are the reviewed package default/capture/cache/publication/provenance integration, not lost trade-disposition work. Complete release-to-main tree equality supplies content proof across the squash boundary.
- Every QA tip adds exactly one report, preserved byte-for-byte in release/main: A1 blob `c832f46ac751764d8d5379cc6c5e94f23785cf69`; B1 `2f9545b5300b4862d58b736f3348ab44c6876e88`; A2 `1cba51bd2071065f851d58368b2fa90c2a251de8`; B2 `3654e2f7cc2c4ce6b7a4b847d2d994b6ef2795cc`. Original report-only commits need not be ancestors because integration cherry-picked their exact report contents.
- Detached baselines have no unique uncommitted work. Ignored dependencies/caches are generated, reinstallable artifacts; persistent test/research databases are outside the candidate trees and remain retained. No raw source notes or private dataset is being discarded.
- Archive directories are standalone EAS snapshots, not linked worktrees. Their indexless Git bookkeeping is not interpreted as user deletions. They remain retained; no recursive archive cleanup is included here.

Recovery: `git branch <recovery-name> <sha>`. If needed, fetch preserved release history with `git fetch origin refs/pull/283/head`; QA report contents also remain on main even if an original local report commit eventually expires from reflogs. Generated dependencies can be recreated with the locked install command; no unique user content is intentionally removed.

## Execution record

At **17:32:23 UTC**, the first ten linked worktrees in the table were removed with ordinary `git worktree remove`, **without `--force`**, after exact-tip, clean-state and linked-path rechecks. The four named builder branches were deleted locally only after their corresponding tree removal. Ignored locked-install dependencies and Python/test caches in those trees were discarded; these are reproducible generated files, not unique user data. The original project, private external scratch databases/research, inspection archives, `release-source` and `integration` remain intact. The published batch branch and evidence branch are not yet removed.

At **17:48:26 UTC**, after completed build/submission verification, `release-source` was removed normally without force following another exact-tip/clean-state/full-tree-equality check. The batch branch `codex/feedback-419-421-20260906` was deleted locally and remotely at the captured `d97459dc`; the remote deletion used an exact-tip lease to refuse a concurrent update. Recovery remains available through PR #283's head and the complete merged content. **Total completed: 11 worktrees, five local branches, one corresponding remote branch.** Final integration cleanup remains planned, and its evidence reference will be retained. No original/nested unrelated tree, private scratch or archive snapshot was removed.
