# Parent specification — counterparty input invalidation

September22,2026. Follow-up to local validated checkpoint9e9f6970. This is a
narrow correctness repair, not a complete prepared-inventory authority receipt
and not a performance/quality gate waiver. The independent actual-route diagnostic
reproduces four failures: a consumed partner board/outlook change leaves A's
completed or running published deck reusable. Four own-input controls work.

## Ownership and scope

Agent A owns the narrow server runtime change and integration evidence. Agent B
owns a new committed regression module adapted from its private actual-route
diagnostic. Agent C independently reviews runtime/tests and adds no overlapping
edits. Parent reviews all changes, runs full tests and decides deployment.

Extend the existing revocable input-epoch mechanism to include the relevant
league-member identities whose stored boards/outlook the worker can consume.
Use the captured execution context's league, not a later mutable session lookup.
Capture dependencies before the worker's corresponding member-board/preference
reads. Keep the caller's original epochs captured before viewer preference reads:
adding partner epochs must never replace a revoked original token with a fresh
token and accidentally revive stale work. Preserve atomic admission and copied
response checks, selected jobs and current force/preserve-running semantics.

A possible minimal seam is an optional participant-ID extension to the existing
capture helper, combined with the already-owned execution context during kickoff.
Use conservative league-member dependency coverage where the worker reads the
whole league. Do not add DB queries, imports from database to server, a new global
all-users invalidation epoch, a new flag, registry of Player objects, schedule,
cache, persistent receipt or generation algorithm. Existing weak-token lifetime
and lock ordering must remain bounded and understandable. Confirm exact identity
sources from actual member-ranking/outlook loaders; do not invent account/co-owner
aliases. If a consumed identity cannot be captured at this seam, report it before
expanding the fix.

## Expected behavior and exclusions

After the existing in-process invalidation of B's global board or league-scoped
preferences, A's dependent old undisposed inventory must fail current admission
and status/publication checks. Normal current work may then be admitted once.
Original persisted impressions, likes, outcomes and exact terms are untouched;
old interest is not revalued or relabeled. The same mechanism protects every arm
using this job path; model configuration and generated inventories are unchanged.

Unchanged inputs still reuse the same job/IDs/order. An unrelated user outside
the captured league must not invalidate A. League-scoped B preferences must not
invalidate B-dependent jobs for another league. Global B board invalidation may
invalidate all B-dependent jobs, consistent with existing global rank semantics.
No-op-save avoidance is not added: retain existing mutation/invalidation semantics.

This only closes dependency coverage for existing in-process board/preference
invalidation calls. Provider roster/pick/market refresh, out-of-process DB writes,
global freshness receipts and authoritative observation timestamps remain separate
known gaps. Do not advertise this change as complete cached-offer freshness.

## Verification

Preserve the private original RED artifact. Committed tests assert desired
behavior, not the old diagnostic's deliberate unchanged-baseline assertion.
Exercise actual kickoff/generator/SQLite B save/status/repeated generate paths:
both complete and truly running published jobs, own-input controls, other-user
and other-league noninterference, selected jobs, and race invalidation after
original viewer capture, during partner input reads, admission, and copied public
projection. Demonstrate mutation of a session/league after capture cannot retarget
dependencies; retain default helper compatibility and weak-token reclamation.

The four existing partner RED cases must become GREEN without weakening original
history/ownership checks. Run existing admission, route, snapshot/publication,
prewarm, replenishment and rollback suites; C independently reviews. Then parent
runs a fresh full suite and source-bound unchanged native/public/persisted worker
comparison. Report new freshness behavior separately from unchanged scoring;
no cold-speed or mutual-acceptance improvement is implied.

## Independent-review amendment: captured league identity

C found the preexisting execution header uses the requested league ID while
the copied session graph is not explicitly checked against it. Headless
replenishment can retain a mutable session reference before capture; a rebound
session could then carry a different league. Base worker reads and owner-context
reads would disagree on league scope, invalidating a dependency proof.

Parent authorizes one fail-closed check in `_capture_trade_execution`: when a
copied league exists, its actual league ID must equal the requested league ID.
Follow the existing changed-user capture error pattern. Do not invent aliases
or register both inconsistent scopes and continue. Keep the existing missing-
league/partial-session failure behavior rather than introducing an incidental
dereference error. Test explicit mismatch and headless rebind before capture,
with after-capture mutation isolation as a separate control. No additional
membership resolver, provider query or authentication redesign is authorized.

## Independent-review amendment: fence explicit board publication

C found early invalidation in tiers/save, anchor/save, reorder and import-apply
precedes the stored member-board write. A new A job can capture a fresh B token,
read the old B rows during that gap, then survive B's publication. Submit has
no current invalidation; rank3 and copy-from-format already have late fences.

Parent, A and C independently confirmed exactly seven explicit server publication
sites: rank3, copy-from-format, tiers/save, anchor/save, reorder, import-apply and
rankings/submit. None is ordinary session-init or replenishment. Parent authorizes
one small server helper used at these seven sites: call the original imported
`upsert_member_rankings` seam with unchanged arguments, and in `finally` invoke
the existing user-global trade-job invalidator. Keep all original early/late
fences; do not move an early viewer protection later. A failed or committed-then-
error write is conservatively fenced, with the original exception preserved under
normal invalidation behavior. Do not change the database writer, add observers,
extra reads, flags or unconditional init refreshes. The original imported writer
remains monkeypatchable. Explicit no-op saves are not exempted or optimized here.

B's named RED launches real A generation after B's early invalidation but before
the actual member-board write; it must establish that A consumed the old DB rows
and is revoked after B's save completes. Test submit, failed/committed-then-error
writes and all seven wrapper call sites without changing payload/confidence
arguments. Existing prewarm/admission checks must remain green. This amendment
extends the original scope to explicit submit and post-publication fencing only;
it does not claim all arbitrary/out-of-process database mutations are tracked.
