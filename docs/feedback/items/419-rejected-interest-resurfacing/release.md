# Feedback 419–421 and small-package presentation — release record

## Authority and current state

The owner explicitly authorized unattended merge, GitHub publication, live delivery and TestFlight where needed for this selected batch. This does not waive review, CI or privacy checks and does not authorize unrelated backlog fixes/closures. The original dirty checkout and private files remain untouched.

**Backend LIVE; iOS 1.17.1 (149) uploaded for TestFlight.** [PR #283](https://github.com/mattmurf77/fantasy-trade-finder/pull/283) merged as `988fa2d690dfa9188f43c33e87dff9d60a5fabaa` after exact-head CI passed. Full independent round 2 passes on `7d3e071f92bac3a087ba63da393109b5eae02f68`; published head `d97459dc` differs only in documentation, and the fetched squash tree equals that published head. [Adjudication and both reports](qa-resolution.md). Exact-source Render deployment is LIVE, the separately authorized presentation setting is **1**, and the exact-build submission is **FINISHED**. Only 419–421 are now `fixed`; Apple tester availability and the physical-device checklist remain **unverified/UNRUN**.

## Intended delivery

- **419:** exact rejection resolves stale interest across server reads and locally observed mobile actions, while deliberate new source interest remains possible. Discovery cooldown and source consent are separate.
- **420/421:** bounded native Win Now initialization/recovery, stale-session protection and neutral timeout wording. This does not fix synchronous backend throughput or remotely update installed mobile code.
- **Smaller packages:** one bounded presentation preference for eligible organic results, retaining all three arms, all offers, explicit selections and valuation rules. Default-off `simple_player_presentment` was separately activated to **1** after deployment and read back. Picks do not count as players. No claim of improved acceptance rate.

[Research and limitations](../../../research/2026-09-06-trade-package-shapes.md), [all-45 read-only audit](open-backlog-audit.md), [batch plan](plan.md).

## Verification gates

1. Resolve confirmed QA findings through the owning builder; root reviews the whole increment. Any runtime change requires a new complete two-agent independent QA round, not fixed-case-only review.
2. Both reviewers pass the full approved test plan; root records tests and line-cited code walks in the test ledger. Consolidate their physical-device checklist without claiming it was run.
3. Fetch main and re-diff all owned paths; preserve concurrent work. Push the reviewed branch through the normal PR workflow. All four CI jobs must succeed on the exact final head before merge; verify the fetched merge tree matches the tested head.
4. Verify Render created a deployment for the merged source, reaches live, and serves new content. Recheck public/operator health and anonymous access refusal. Preserve all prior 207 effective flags, 258 existing config values, tiers and experiments.
5. Activate only `simple_player_presentment=1` using the existing audited admin-config command, then verify the single-key delta. Rollback is that key to 0 for new compatible generation; retained old job IDs keep their captured order.
6. Build from a clean, tracked-only checkout of the reviewed final source. Recheck EAS version race, all native version fields, effective production config, archive privacy and mobile byte identity. Submit the exact resulting build ID once; verify submission status before any retry.
7. After verified delivery, mark only 419, 420 and 421 `fixed` through the existing admin API and read each back. Do not set `shipped` or close any unrelated audit item.

Build completion, App Store Connect upload, Apple tester availability and a physical-device pass are separate facts. The last two remain unverified until evidence exists. No simulator/Maestro/captures under D-056.

## Read-only preflight

2026-09-06 15:53 UTC: Render `srv-d7g37ftckfvc73a32gvg`, live deployment `dep-dae3oseq1p3s73fs3m50` on `4026ebc8`, not suspended. Public/operator checks passed; unauthenticated trade/admin reads refused with 401. The complete 207-flag/258-config snapshot matched the earlier snapshot, as did tier and experiment hashes. The new presentation key was absent. No production mutation occurred.

Archive-only inspection of `aa463789`: 2,677 files, all 631 tracked mobile files byte-identical; only EAS-created one-commit shallow Git metadata is untracked. No local credentials/env files, raw interview notes, dependency trees or local databases. Effective config: version 1.17.1, production API, test mode false and existing project/bundle/owner identity. Inspection is not an upload; final source must be revalidated after QA repair.

Repaired source `7d3e071f` archive independently verified: 2,682 files and all 631 mobile files byte-identical; no unexpected/private artifacts and one-commit archive history at the exact SHA. GitHub admin/push access and unchanged main verified; latest EAS counter remains 148. GET-only production checks at 16:41 UTC again pass with all historical settings preserved and new knob absent. Public in-app-browser landing renders with no captured warning/error logs; no login or user action performed. Root read-only privacy/history audit covers all 96 final and commit-history paths, with no private transient paths, credential artifacts or unrelated runtime changes.

Local full backend results: root **5,645 passed / 1 optional skip**, independently repeated by both round-2 reviewers; each focused matrix **892 passed**, all 95 mobile guard programs, TypeScript/testID and 190 web checks green. The 23-step consolidated [physical checklist](testflight-checklist.md) is authored, reviewed and **UNRUN**. No simulator or physical-device pass is inferred.

## Verified publication and build dispatch — 2026-09-06

- Final published head **`d97459dc9f72ebe158f70fcbb86f29051659c206`** passed [all four CI jobs](https://github.com/mattmurf77/fantasy-trade-finder/actions/runs/34047364058): backend **5,645 passed / 1 skipped in 717.99 s**, mobile TypeScript/all 95 guards, testID lint and 190 web checks. The optional offline-backtest skip remains disclosed. Hosted action-runtime deprecation annotations did not fail the jobs; no unrelated CI upgrade was made.
- PR #283 squash-merged at **17:16:56 UTC**, source **`988fa2d690dfa9188f43c33e87dff9d60a5fabaa`**. Fresh fetch and complete tree comparison against `d97459dc` returned no differences. No direct-main push or check bypass.
- The squash message inherited three literal skip markers from earlier documentation commits. Render's commit-triggered auto-deploy remained enabled but no deployment was created. This matches [Render's documented skip-message behavior](https://render.com/docs/deploys#skipping-an-auto-deploy). After confirming no duplicate/in-progress deployment, root triggered the exact merged SHA once using the [deployment API](https://api-docs.render.com/reference/create-deploy), preserving cache and service settings. HTTP 201 at **17:20:04 UTC**, deployment **`dep-daeq1h740ujc73897oog`**, initially `build_in_progress`; live verification is separate.
- Final archive `archive-d97459dc` independently checked by QA-A and root: **2,684 files, 631/631 tracked mobile byte-identical**, no missing/different/unexpected/prohibited files, only one shallow retained commit at `d97459dc`. Effective production identity/version remain correct. Historical tracked `.claude/settings.local.json` is byte-identical to public baseline, contains only `permissions.allow`, and has no credential-pattern hit; it is not a newly copied local secret.
- iOS **1.17.1 (149)** [EAS build `87f9ce05-f91f-4bbd-8c1a-bc7c49932e2d`](https://expo.dev/accounts/mattmurf77/projects/dtf-dynasty-trade-finder/builds/87f9ce05-f91f-4bbd-8c1a-bc7c49932e2d) created **17:19:23.821 UTC** from clean exact `d97459dc`, after CI and squash-tree verification, reusing frozen signing credentials; **FINISHED 17:25:01.357 UTC**.
- Initial exact-ID submit scheduling rejected the optional release-notes/changelog parameter as Enterprise-only. A read-only submission-history query at **17:30:07 UTC** confirmed no new submission had been created. Root omitted only that unsupported optional field, without changing plan, billing, credentials, app code or profile; standard exact-ID submit then created [submission `a07afa27-7b21-47d8-9fb9-8e17518232b6`](https://expo.dev/accounts/mattmurf77/projects/dtf-dynasty-trade-finder/submissions/a07afa27-7b21-47d8-9fb9-8e17518232b6). Independent readback at **17:34:02 UTC**, repeated by root at **17:40:08 UTC**, verifies **FINISHED**, `error:null`, correct iOS project/owner/Apple app. No duplicate build or submission, tester-group change or App Store public release was performed. Apple processing/tester availability remains unverified.

## Verified backend and single-key activation

Deployment **`dep-daeq1h740ujc73897oog`** reached LIVE at **17:21:19.905609 UTC** on exact merged `988fa2d6`. At 17:22:30 UTC, public/operator smoke passed, anonymous trade/admin reads returned401, all existing 207 flags/258 config values/tier/experiment hashes matched the previous production snapshots, and the newly seeded setting was **0**.

The reviewed `scripts/set_knob.py` performed exactly the approved **0→1** presentation change through the authenticated logged/reloading admin API; CLI timestamp **17:23:58.015131 UTC**, audit source `feedback-419-421-simple-player-v1-20260906`. The initial local attempt found no script in the original dirty checkout and made no HTTP request. The successful call used the tracked reviewed CLI and passed the original credential only in its child environment; no secret file was copied into the release checkout.

At **17:24:18 UTC**, readback verifies **`simple_player_presentment=1`**, no changed existing flag/config key, unchanged tier/experiment/root hashes, present event-ID index and zero ingest transaction failures. [Sanitized smoke](production-smoke.json). The existing experimental personal-market flag and all three arms remain preserved. This changes eligible fresh organic presentation; it does not reorder retained old decks, cap large deals, change picks/selected searches, or establish acceptance improvement. Rollback is only this key to0 for fresh compatible jobs.

Independent GET-only verification at **17:33:55 UTC** repeated these results. At **17:34:21 UTC**, Render metadata still reports auto-deploy enabled, commit trigger, main branch and not suspended. The activation timestamp above is the CLI request timestamp, not an independently fetched database audit-row timestamp.

## Selected feedback closure

After upload completion, the existing admin API accepted and a narrow readback confirmed only these transitions. `fixed` means the fix is in the next update; it does **not** mean the tester has installed or verified it. No record was marked `shipped`.

| Feedback | Status | Server update timestamp (UTC) |
|---|---|---|
| 419 | fixed | 2026-09-06 17:41:48.077159 |
| 420 | fixed | 2026-09-06 17:41:51.397001 |
| 421 | fixed | 2026-09-06 17:41:56.234037 |

The all-45 backlog audit remains research-only; none of its unrelated closure candidates was changed.

## Recovery and remaining evidence

### Resolved publication approval blocker — 2026-09-06

Prepared release head **`e5294748477ece417ea5e10d4f20ba7b1b148c31`** is clean, passes whole-range diff hygiene and is runtime/test/config-identical to the independently reviewed `7d3e071f`. The attempted fetch/push/PR command was rejected **before process creation** by the safety review: the conversation's GitHub publication authorization was not accepted as explicit permission for this exact public destination. No part of that command ran; no push, PR, CI, merge, Render deployment, config activation or EAS upload occurred. The rejection was not bypassed or retried through another route.

Read-only local verification confirms the configured origin is `https://github.com/mattmurf77/fantasy-trade-finder.git`. Publishing to a public repository makes the scoped source/tests/sanitized documents publicly accessible. The owner subsequently answered **“Yes”** to explicit approval naming that public destination and the reviewed code, tests and sanitized documentation, followed by CI, Render and TestFlight. **The destination-specific approval blocker is resolved.** The next attempt uses the same normal publication workflow; CI and privacy gates are not waived. Preserve original dirty files and private research.

Eleven verified temporary builder/baseline/QA/release-source worktrees, five local batch branches and the corresponding published release branch were removed after advance recovery capture and exact clean-state/content rechecks. [Recovery ledger](../../../recovery/2026-09-06-feedback-419-421-release.md). `integration` remains until the final evidence PR merges; its final cleanup is separately pre-recorded. Original dirty checkout, private scratch research/databases, inspection archives and the concurrent Fleeced organization branch are untouched. Superseded documentation PR #282 was closed after confirming its head is included in PR #283; its branch was not deleted. Do not build from the original dirty checkout or publish private scratch research.

Completed: exact-head CI/PR/merge, source-specific Render deployment, single-key activation, exact EAS build/upload and selected status readback. Remaining: Apple tester availability and the **23-step physical-device checklist**, still **UNRUN**. Backend smoke does not demonstrate native UI behavior, production latency or improved trade acceptance. Release bookkeeping is documentation-only and must not trigger a second binary build or change runtime settings.
