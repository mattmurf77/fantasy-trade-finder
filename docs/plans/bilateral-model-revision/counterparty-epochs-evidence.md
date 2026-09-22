# Round 8 — consumed counterparty epoch coverage

September 22, 2026. Parent scope: `spec-round8-counterparty-epochs.md`, including
the independently reviewed captured-league identity amendment. Starting local
checkpoint `9e9f697007e26797857dbc1611fda86e504bc29e`; no deployment/activation.
Agent A owns server runtime/evidence; B owns committed regression tests; C is
the independent reviewer. This is a correctness repair, not a latency claim.

## Prior RED and implementation boundary

The preserved private witness in `prepared-inventory-regression.md` proved four
counterparty failures against actual admission, revision generation, SQLite saves,
public status and repeated organic generate. B adapted it into
`backend/tests/test_trade_counterparty_epochs.py` before runtime changes: four
partner cases failed, four matching viewer controls passed in1.84s. The private
artifact is unchanged; committed tests assert the desired freshness behavior.

The existing weak revocation token mechanism now accepts optional exact
`participant_ids`. The default helper still captures the viewer's original two
scopes. A kickoff resolves its already-owned execution context, then adds each
captured league member's global board token and same-league preference token
before the worker reads the corresponding stored boards/outlooks. It unions
those tokens with the caller's original pre-read viewer tokens. Revoked original
tokens are never replaced by fresh tokens, so an edit racing viewer preference
resolution cannot revive stale work.

The worker reads member boards by `member.user_id` after its league-scoped
`load_member_rankings`; outlook and owner preference loaders use those same
captured member IDs. No account/co-owner/provider aliases are inferred. Capture
uses the owned execution league, not a subsequent mutable session lookup. The
whole captured member set is conservative because worker preparation can read
the whole league even for a selected/opponent-scoped job.

Existing invalidation still revokes its direct owner's matching jobs, preserving
legacy jobs with no captured tokens. It additionally revokes jobs retaining the
**specific token just invalidated**, clears their published cards and removes
their organic pointers. It does not scan for any arbitrary previously revoked
token and re-revoke unrelated jobs. A global B board edit reaches B-dependent
jobs across leagues; a B preference edit for L1 reaches only that scoped token.
Other users outside the captured member set remain unaffected.

Original public/admission/copied-snapshot and terminal fences consume those same
token objects; `_TradeInputEpoch.__deepcopy__` preserves identity. No scoring,
enumeration, weights, versions, order, proof JSON, budget, impression/outcome
schema or historical action identity is changed. A known input mutation now
withholds stale undisposed inventory and admits current work; it does not alter,
reprice, relabel or delete original durable impressions/likes/outcomes.

## Independent-review amendment

C traced a preexisting headless-session rebind: the requested execution header
could name L1 while its copied league object had become L2. Primary worker and
owner-context reads would then use inconsistent league IDs. Parent explicitly
authorized a narrow fail-closed copied-league identity check in the existing
execution capture function. The mismatch follows the existing changed-user
RuntimeError pattern; no dual-scope registration, alias guessing or extra source
resolution is allowed. An absent league retains the original missing-state
worker failure instead of failing at the new member enumeration.

C also identified a concrete post-publication race: the four early-invalidating
board routes can admit a new A job after B's token is revoked but before B's
updated member rankings are committed. That job captures a fresh token and can
consume old rows. Parent wrote a second explicit amendment for a finally fence
around the seven explicit server publication sites only: rank3, copy-from-format,
tiers/save, anchor/save, reorder, import-apply and rankings/submit. The common
helper must preserve the original imported writer seam and exact payload/
confidence arguments, and retain all prior early/late fences. Failed and
committed-then-error writes receive the same conservative post-attempt fence.
Session-init/replenishment, the database writer and unrelated modules are not
wrapped. Submit previously had no fence; it is explicitly included in this
amendment rather than hidden under the original existing-invalidator scope.

## State, privacy and cost

No database query, new import, flag, scheduler, cache, full-inventory receipt or
process-wide all-user epoch was added. The weak index contains scopes only while
jobs/admissions retain their tokens. Capture is O(captured members) with two
scopes per unique identity; token lists contain only small revocation objects,
not Player/board/league/proof references. Multiple jobs can share the same scope
token. An invalidated old token can remain alive with its existing retained job
until normal cleanup; replacement work gets a new token without reviving the old.
There is no new hard memory bound beyond that existing job lifetime.

Invalidation already scanned jobs; it now also compares the job's bounded member
token list by identity. Capture/registry changes are inside the same job lock,
with input/provider/database reads and worker startup outside it. This is not
a distributed invalidation protocol and does not interrupt a constructor
immediately when its publication authority is revoked.

## Verification status

Initial author focused group: **101 passed in7.98s**, including the eight actual
route cases and existing admission/prewarm/replenishment/publication/rollback
coverage. This precedes the final race/identity tests and is not final acceptance.
B's expanded tests, C's final review and the parent's fresh full suite and
unchanged native/public/persisted worker comparison are recorded below when done.

After the captured-league guard, the interim group had54 passing and one
preexisting expectation requiring its authorized update: the unregistered
league-override case now fails at capture with `session league changed before
trade job started`, rather than reaching the old late `Unknown league` engine
error. Both are errors, but the earlier failure prevents mixed-scope input reads.
Missing-state controls still retain their original worker error.

The post-publication amendment's two named RED controls were then preserved
before the helper existed: actual tiers/save launches and completes A generation
inside the imported writer seam after early invalidation, proves A consumed B's
old1700 board, then commits B's changed board; explicit submit separately
publishes1400 with no fabricated early invalidation. Both previously retained
A's old public deck and failed `assert_revoked` (2failed in1.32s).

After the helper and all seven call-site switches, the author expanded focused
group is **143 passed in10.66s**. It includes the named publication/submit guards,
counterparty and viewer actual-route controls, selected jobs, input/admission/
copied-projection races, captured-session mutation, scoped noninterference,
weak-token reclamation, missing-state behavior, original admission/prewarm/
replenishment/publication/rollback and submit authorization coverage.

Runtime source at this point:
`backend/server.py` SHA256
`0b24ad25d90c23e2306282d6d96f30f99414da6d046cc971cf92710ace6f2ea6`.
`git diff --check` passes. The runtime diff is51 insertions/17 deletions in this
one file, including comments and seven call-name substitutions. No constructor,
presentation, pricing, database or mobile source is edited by this repair.
Independent final review, final helper/error contracts and parent full-suite/
actual-worker parity remain pending at this intermediate evidence point.

Final B-owned focused module: **61 passed in4.72s**. Test SHA256
`8758eecf22f7e0f4c1e75d3fc1c26a3308035dadbc2cd97250a3535f8cb48d5f`.
This adds actual failed-before-write and committed-then-error tiers/submit
controls, exact argument/reference forwarding and preserved writer return/
exception identity, plus seven AST call-site contracts and a census preventing
init/replenishment or other raw writer coverage from being silently changed.
One initial AST fixture used `ranking_payload` for import-apply; immutable HEAD
confirmed its existing argument is `_import_payload`. B corrected only that
fixture before the final61 pass. Parent separately updated the existing scoring-
context test's intentional earlier mismatch error; B did not modify it.

All nine named RED failures are now GREEN: four consumed-partner board/outlook
cases, three copied-league mismatch cases, and the real pre-publication-gap and
explicit-submit cases. The runtime remains frozen at `0b24ad25…`; no author
subprocess or source/CPU guard is active. Parent owns the subsequent guarded
large worker/native/off/failure comparisons and full suite; those are not
implicitly covered by this focused result.

C's final independent review is **CLEAR**. C ran **188 focused tests in10.34s**,
binding server `0b24ad25…` and new test module `8758eecf…` unchanged before/after.
The review traced exact member-ID source usage, preserved original viewer tokens,
owned capture/admission/copy races, scoped token lifetime and all seven final
publication fences. Both independently discovered amendments are resolved within
their written scopes. C made no source edits and released its guard to parent.
Runtime, tests and this agent's integration evidence are now ready for the
parent's final source-bound parity and full-suite gates; no release is implied.

Parent subsequently completed all five source/HEAD-bound native/worker/off/
failed-write controls and the fresh full suite: **6,861 passed/1skip in364.43s**.
Every retained native/public/complete persisted comparison and publication prefix
matches round7; failed first evidence write exposes/stores zero cards. Mobile
TypeScript/all99 structural suites/test-ID lint and web195 also pass. Final
[round8 validation](validation-20260922-round8.md) records source hashes, exact
comparison exclusions and remaining unexecuted production/CI/device gates.

## Explicit remaining exclusions

This closes only dependency coverage for **existing in-process** member board
and preference invalidation calls. Provider roster/pick/market changes,
out-of-process writes, complete authoritative freshness receipts and observed-at
contracts remain separate known gaps. No-op saves retain existing invalidation
semantics. No warm or cold three-second result, mutual-acceptance improvement,
production stale-offer rate or release clearance is inferred.

Source-only follow-up at server `0b24ad25…` confirms that **job-path coverage is
not whole-engine coverage**. `GET /api/trades` (`server.py:15446`) reads the
session service's retained cards via `TradeService.get_pending_trades`
(`trade_service.py:7802`). Its owner filter checks model/version, matching proof
and `owner_published`; it then applies dispositions and current significance.
None of those steps consults job input epochs. `_revoke_trade_job_locked`
(`server.py:3033`) clears the job's public card list, not the shared service's
action store or an already-set card publication marker. Thus input revocation
alone does not fence this separate pending-card projection.

Synchronous `POST /api/trades/asset-ideas` and `POST /api/trades/fair-packages`
call `_owner_selected_ideas` directly (`server.py:14688`, `15316`, `15007`), not
`_kickoff_trade_job`. They retain frozen-context owner revalidation, downstream
checks, durable impressions and pre/post-persistence model/version fences, but
capture no revocable member epochs. Their generated run ID is used as a ledger
`deck_job_id` (`server.py:14995`), without registering a job or linking the cards
to job revocation. The round8 selected-job tests cover pinned/opponent-scoped
generation through kickoff, not these synchronous surfaces. These exclusions
were verified by source tracing only during the parent's full-suite window;
no additional runtime change, regression run or broader freshness claim follows.

The copied-league guard also has a precise admission boundary: a mismatched
new execution context cannot start a worker, but `_kickoff_trade_job` may return
a compatible preexisting L1 job before handling the new capture error
(`server.py:9071–9095`). This retains the original completed-cache/running-job
adoption rules; the reused job keeps its own captured L1 context and epochs.
With supplied matching preferences, an L2-rebound session can therefore receive
the existing L1 job ID rather than a capture-error job. Source tracing proves
that error-response distinction, not stale or wrong-league generated output.
Parent explicitly retained valid-cache adoption; no additional admission-policy
change or test is part of round8.
