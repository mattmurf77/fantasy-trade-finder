# Validation — persistent prepared trade inventory

## Final interaction revision — 2026-09-23

Prepared-focused suite:526 passed85.57s. Subsequent matched-like and two admission
race controls plus parent runtime:13 passed7.07s. The roster race was RED before
pinning the original local read guard before admission. Explicit-board baseline
is also captured before strict full admission; neither guard is re-blessed later.
Final typed failure diagnostics/feedback/runtime58 passed7.12s, including15
RED-to-GREEN cases proving the new typed codec errors retain fixed safe reason
codes without raw exception text.

Actual936 telemetry-ON native preparation/adoption after the fused index and
interaction fixes: prepare23.741954s, seal12.650800s, attestedopen0.155895s,
first30durable0.999153s, **first30 published1.068854s**, fulladoption21.900529s.
All936 native proofs/terms/order/expiry preserved; candidate133496B,
maxSQLbind995984B, peakRSS343703552B. Publication timing observes the first
job-lock release containing the30 public cards; it excludes HTTP transport,
mobile polling and rendering. Run46.69s; no production latency claim. The only
subsequent runtime edit recognizes typed errors in sanitized operator diagnostics.
Final dense repetition and hosted release gates remain pending.

The final dense repetition on570778f2 subsequently PASSED703.75s, all13728 native
offers preserved. Preparation364.224327s (worker169.368429s/seal194.689049s),
attestedopen1.609288s, first30durable2.431208s, first30published2.502433s,
fulladoption338.260348s, maxSQLbind999044B, peakRSS1433731072B. Telemetry OFF;
synthetic fixture's native `trade.presentment_rules` OFF. The prepared R4 projection
still ran unconditionally in that measured revision, a subsequently corrected
flag-off compatibility issue. This dense capacity fixture is not a replica of
production flag state. Full original proof/order/expiry parity and zero fake
actions passed; no dense telemetry capacity or device3sec conclusion follows.

Independent final review reproduced two actual flag-off parity failures: a pending
match and eight-day awaiting like survived native Bilateral2 construction but were
wrongly excluded by prepared admission. The correction gates only prepared R4
history/cuts on the same existing flag. Exact pass/source-interest checks remain
unconditional. Positive R4 tests explicitly enable the flag. A smaller native
telemetry-ON/presentment-ON run will qualify that final predicate under both active
production switches; hosted CI must rerun on the final commit before merge.

Both-switch-ON final936 repeats passed full parity, with variable local latency:
unprofiled first30published3.282466s/full31.969205s/prepare25.600180s/RSS305594368B;
instrumented repeat first30published1.175086s/full24.644787s/prepare28.941242s.
Both retain all936 cards/candidate133496B/maxSQLbind995984B. Do not attribute the
variance to the flag: earlier unconditional R4 already did the same empty-history
reads. In the instrumented first prefix, all11 history projections totaled0.0095s,
receipt calls0.0239s inclusive, evidence binding0.3296s and checkpoint0.0626s.
This is neither a reliable3s SLO pass nor a production/phone measurement. No
further optimization is justified by these two observations alone.

Hosted570778f2 CI35811257235 ran Python3.12.14:7402 passed/1 skipped/5 failed
in874.09s; mobile/web/test-ID passed. Four failures were the legacy race-test
projection stub rejecting a new prepared=False keyword on ordinary jobs; keep
the old three-argument call for non-prepared jobs (four local REDs reproduced).
The fifth overlapped cleanup of an immediately stale synthetic session; exact
reproduction and fixture-only correction are tracked before retry. No deployment
or cache activation follows a failing CI run. Four legacy race cases were
reproduced locally RED, then23 compatibility/feedback/runtime/race cases passed
16.66s after retaining the ordinary three-argument seam. Forced janitor eviction
reproduced401 session_expired for the zero-timestamp fixture (one RED3.66s);
registering both interactive test sessions with current wallclock then passed
all12 chunk/feedback cases35.65s. Authentication, runtime cleanup and event/action
assertions are unchanged. Final PostgreSQL59 passed16.10s on current codec/store;
the disposable server was gracefully stopped with its data/log retained.

## Current revision — implemented v2, qualification pending

The owner explicitly approved the persistent chunked-storage/lifecycle subsystem
after the initial implementation hold. The [saved plan](chunked-storage-plan.md)
preceded resumed code. New v2 codec, store and runtime paths now exist locally;
this is not a release, activation or successful production-cache claim. Production
caching remains OFF after the second canary. Historical v1 results below do not
qualify this new subsystem.

Implemented boundaries requiring final integration qualification:

- Full native offer inventory and order, proof/valuation strings, original IDs,
  source links and snapshot representations are retained. Incremental capture
  uses byte-bounded pages and a lazy public projection rather than an additional
  complete envelope. Candidate-set JSON remains a bounded, byte-exact singleton.
- Complete bounded semantic validation precedes sealing against an already pinned
  descriptor root. It verifies all cards/evidence, candidate and compact-admission
  correspondence, and the scoped diagnostic DAG. Byte/node/depth and repeated-reference
  amplification checks precede materialization; cached subtree height cannot bypass
  the depth bound. Only the sealer can mint the reserved versioned attestation.
- Fast admission checks the recognized store attestation and every authenticated
  compact disposition entry without scanning native proof pages. Full native
  proof/evidence/diagnostic checks, exact index correspondence and authoritative
  batch re-read remain mandatory before evidence commitment. A corrupt late page
  may leave an earlier valid prefix, never the affected batch or a mixed fresh
  suffix. Trailing disappearance must report incomplete adoption, not a short
  success. Only durable evidence advances the separate real-card and ghost cursors;
  all ghost evidence must complete. Exact retries retain original publication time
  and recover evidence committed before a checkpoint crash.
- Live generation/adoption work renews its existing token without extending
  artifact expiry or reviving stale claims. Staging never replaces ready data;
  seal/head replacement is atomic. V1 parsing/limits and its fallback adoption
  path remain separate, not silently migrated into v2.
- The in-memory janitor leaves private preparation under its live 300-second
  persistent claim and same-token renewals. V2 adoption resets the 60-second stall
  timer only after durable batch/checkpoint progress, not reads or polls; ordinary
  generation retains its existing timeout. Hourly expiry/abandoned-stage cleanup
  continues while rollout is OFF, without discovery, refresh or generation.
  Expiry controls eligibility; physical removal awaits the next successful pass.
- Every consumed participant is deletion-indexed before private staging writes.
  V2 staging/validating/sealed/retired content participates in deletion and pruning;
  exports omit private payloads/receipts/recovery fields and tokens. A pre-v2
  binary downgrade needs verified purge or a deletion-compatible bridge, not only
  an OFF flag.

Initial full-admission-v2 Lane C source-bound result: **114 passed in 9.79s**, combining the unchanged
v1 payload/capture tests, new v2 payload tests and independent graph controls.
Codec SHA-256 `8723c50dd20ca3e996abf71a1dc261258793c3111944552d1238c3f71407b335`;
owned test SHA-256 `99635407d712dd31fe7d9c326edea97188cdf29380dd6d5f1edbcffddb498dc2`.
The independent warmed-depth control failed before the height repair and passed
afterward; the amplification control verifies refusal before materialization.
The 100-card query-count control verifies header checks are bounded by iteration/
batch boundaries, not performed for every card. These are codec results, not a
whole-release source manifest or dense end-to-end performance result.

Revised attested-admission codec: **140 passed in 10.87s** in the same combined
payload/capture/graph group, at codec SHA-256
`0b885d84fdbc7ed9f88261d0636083dce4d9ff78a8ec59bad00b51ed17e50f6a`
and owned tests `d70a72e4a08735008775ce23373346ea993e27f015263e904dda0b8dfd030e9c`.
New controls cover exact compact-index fields, whole-index uniqueness/count/expiry,
missing/unknown attestation, no native/diagnostic reads during fast opening, and
full native validation at publication. Author controls and an independent real-SQL
test first reproduced silent short completion after trailing evidence disappeared;
terminal real/ghost count checks now reject that path. Independent store/runtime
and whole-release qualification remain separate from this codec result.

Initial full-admission-v2 actual-constructor check: 936 offers from 3 synthetic teams with 24
players each completed exact prepare/adopt proof/order checks. Local preparation
22.36s included 12.24s sealing; adoption preflight 12.45s, first 30 durable 17.06s,
full adoption 37.84s, peak RSS 270,221,312B. Recorded worker phase 10.05s is not a
separately controlled ordinary-generation comparison. Telemetry was OFF, and this
is neither the 13,728-offer qualification nor a successful speed result. Raw local
evidence: `/private/tmp/prepared-pressure-20260922.1q17fw/chunked-small.log`.
These timings triggered the plan's measured admission revision. They are not
measurements of the new attested opener, and no latency savings are inferred.

### Revised 936-offer qualification — telemetry ON

The actual native constructor, complete preparation/seal, attested admission and
full adoption passed for all **936 offers**, preserving every proof, term and
original order. This local synthetic run explicitly enabled suggestion telemetry;
its exact candidate singleton contained 936 members and 133,496 UTF-8 bytes.

| Measurement | Observed local result |
|---|---:|
| Complete preparation | 23.7855s |
| Worker phase | 11.0985s |
| Capture finish, within worker | 2.7309s |
| Seal validation | 12.6430s |
| Attested opener | 0.1461s |
| First 30 durable offers | 1.08137s |
| Full adoption | 22.1519s |
| Largest capture callback | 100 rows / 2,887,883 serialized bytes |
| Largest observed SQL bind | 995,984 bytes |
| Peak process RSS | 274,726,912 bytes |

Raw evidence: `/private/tmp/prepared-pressure-20260922.1q17fw/attested-small-telemetry.log`.
The earlier 17.06s first-30 result had telemetry OFF; this 1.08137s result has it
ON. They are different qualification runs, not a strict same-configuration
experiment or an isolated speedup ratio. First durable SQL publication is not
phone tap-to-actionable latency. This passes the measured 936-member candidate
dependency, not every possible singleton or dense-inventory capacity. The full
native generator and cumulative published-card memory remain outside the bounded
transport guarantee. The completed telemetry-OFF dense run is reported separately below.

### Dense baseline, completed attested run and remaining gates

The initial dense v2 baseline prepared/sealed all 13,728 offers in 348.85s
(worker 160.60s, seal 188.03s), maximum observed SQL bind bytes 114,252 and peak
RSS 1,412,857,856B. Its superseded full-admission phase was interrupted after
389s before the first card. This is preparation evidence, **not a full adoption
pass**. Revised admission requires a fresh full dense qualification; no result
from the interrupted path is relabeled as revised-path success.

The subsequent attested-admission run completed **all 13,728 original offers**
with exact proof, term and order parity in 701.13s end to end. It used the actual
native constructor and unchanged search budgets, with telemetry OFF:

| Measurement | Observed local result |
|---|---:|
| Complete preparation/seal | 361.35s |
| Attested opener | 1.536596s |
| First 30 durable offers | 3.854723s |
| Full adoption | 338.64s |
| Largest observed SQL bind | 999,044 bytes |
| Peak process RSS | 1,492,434,944 bytes |

This is a full dense correctness/capacity observation for that isolated local
run, not a phone-latency or concurrent production-capacity guarantee. Its first
durable batch remained above three seconds locally. Telemetry OFF means dense
candidate-singleton capacity remains unmeasured; the separate 936-member ON run
above is the actual candidate dependency evidence. Full native generation and
cumulative published-card retention still dominate potential total memory; the
approximately 1.49 GB observed process peak is not a bound on production memory.

The subsequent locally implemented change fuses current-disposition checking into the
existing complete authenticated-index scan to remove a second index traversal.
Its callback remains bounded to 100 immutable entries, and an unverified current
disposition is a cache miss, not stored corruption. The dense results above
precede that change; no improvement is inferred until it is measured again.

Final gates remain: whole-release store/runtime/lifecycle acceptance, isolated
PostgreSQL qualification, final-source validation of the fused admission path,
full backend and exact-head hosted CI, then reviewed deployment and
fresh-key canary. Record phase timings, maximum SQL statement bytes and peak RSS.
Native constructor retention and cumulative published-card retention remain full
inventory costs. The owner logger caps capture callbacks at 100 rows, not an
aggregate byte budget before diagnostic compaction; page limits do not bound that
additional callback-local graph. Bounded page transport does not prove the current
instance can safely run the dense workload or meet the three-second first-action goal.

Source: [codec](../../../backend/prepared_trade_payload_v2.py),
[store](../../../backend/prepared_trade_store_v2.py),
[interactive adoption](../../../backend/prepared_trade_runtime_v2.py), and
[account export/deletion](../../../backend/accounts.py).

## Historical first-release gates and live canary

PR305 tested head18045139: hosted CI35788148359 passed all four gates,
backend **7,144 passed /1 skipped** in817.12s. Earlier final local full7132/1skip,
subsequent focused privacy/store/deletion131, runtime/replenishment39 and independent
export10 all passed. These supersede the historical pending-suite notes below.
Merge4903d205 is tree-identical. Render became live22:07:49UTC.

The production canary nevertheless exposed `prepared_payload:snapshot_conflict`
across captured batches and saved zero inventories. Prepared rollout is off again;
ordinary generation unchanged. This real-world failure is not qualified by the
passing synthetic suites. [Release evidence](release.md) records exact rollout,
coverage and required corrective gates. Device latency remains unverified.

## Historical v1 corrective capture/adoption qualification

The actual logger64-card case reproduced the live `snapshot_conflict`; a real
512-card varied-DAG case then reproduced the downstream SQL collision after30.
Capture now reconciles equivalent expanded scoped content atomically. Adoption
persists the frozen original graph and only the currently referenced dependency
closure, retaining strict SQL row identity. No generator/policy/ranking change.

- Parent combined cache regression: **321 passed in41.43s**.
- Independent capture/review group: **91 passed in5.26s**;8RED/1GREEN before repair.
- Independent store/review group: **108 passed in12.44s**; all4 capture→SQL
  partition/restart controls failed before repair and passed afterward.
- Actual512-offer prepare→SQL adoption now completes all512 with exact proofs,
  terms/order and no truncation; first30 commit2.031s, full5.516s locally.
- Web195/195; test-ID lint passed. Full backend and exact-head hosted CI are
  recorded below as pending at this checkpoint; the subsequent corrective release
  and second failed canary are summarized next.

Negative controls retain rejection of foreign scope, altered content/checksums,
malformed dates, missing/cyclic references, partial state and changed persisted
row bytes. Valid different observation times retain the original snapshot time;
impressions use the original actual-adoption time. A64-collision check pins two
graph validations per conflicted batch rather than a graph walk per collision.
Local stress is synthetic32-opponent SQLite with provider/full receipt mocked;
it does not establish the live three-second first-action KPI.

PR306 subsequently passed local 7183/1skip and hosted 7183/1skip with all four gates
green, then deployed merge `2cff90c7`. The second canary passed the prior capture
conflict but failed with `InvalidArtifact`, zero artifacts; the precise cause was
not logged. Rollout was disabled again. Separately, the actual dense synthetic
constructor produced 13,728 offers and a 461,530,265-byte logical /15,083,835-byte
compressed-text envelope with 2,325,421 JSON nodes. It exceeded the whole-copy
node guard before save. This reproduces a capacity defect, not the unproven cause
of the second production failure. That fixture had telemetry OFF and establishes
no candidate-singleton capacity result. See [release history](release.md) and
[the bounded-storage plan](chunked-storage-plan.md).

2026-09-22. Local implementation evidence, not deployment or activation evidence.
Baseline: `ff122752`; release owner remains the parent agent. See [scope](scope.md).

## Historical v1 executed lane evidence

Pre-merge privacy amendment: prepared inventory/target exports now retain only
owned metadata (not private payloads), and impression exports remove only the new
`prepared_runtime` recovery field. Two named privacy tests failed before repair;
131 store/account-rights/deletion tests pass after it. Stored data is unchanged.
Unattended replenishment retains its existing generation path rather than adopting
as an interactive request;39 runtime/replenishment tests pass. Fresh full local
run:7,132 passed /1 optional-data skip in434.21s before these final narrow guards;
exact-head hosted CI remains required for the final amendment.

Parent integration checks, 2026-09-22: 172 passed (runtime, independent real
headless preparation/adoption, store, and counterparty epoch regression), followed
by 85 passing runtime/epoch tests after failed-action and pending-read hardening.
An earlier full-suite run reported 7,097 passed / 1 skipped / 2 failed while
the read-guard fixture was being updated; it loaded the old fixture and its source
locations no longer matched. The corrected fixture passes independently. A fresh
whole-suite run and exact-head hosted CI remain release gates, not inferred passes.
Web structure:195/195; preserved mobile test-ID lint:passed. No simulator work.

Independent broader regression:393 passed after fixture-map parity and a fresh
process removed seven concurrent-source inspection failures. Store:80 tests
including bounded decompression, corruption, rollback and a named unsafe-decoder
negative control. PostgreSQL schema/conflict/lease SQL compiles offline; live
PostgreSQL runtime/load is still unverified until deployment/canary.

Production preflight at21:18:45UTC verified Render ff122752, exclusive Bilateral2,
unchanged uncapped presentation settings, one Standard instance, autodeploy off.
No cache rollout mutation had occurred at that check.

| Check | Observed result | Scope / limit |
|---|---|---|
| Cohort/source focused suite | **56 passed**, 0.10 s | Network-denied tests; injected source, credentials and clock. Includes final reserve/taxi dependency amendment. No production reads. |
| Independent cohort review | Clear after repairs; 53-case predecessor plus final three cases passed | Two independent runs cover all 56 current cases, not a claimed single 56-case rerun. Final availability selection: 3 passed / 53 deselected, 0.04 s. |
| Independent payload suite | **68 passed**, 3.20 s | Exact runtime/public/evidence roundtrip, diagnostic dependency checks, immutable original terms and ordered batching. Not an adoption latency benchmark. |
| Lane C author capture group | Reported **71 passed**, including three real worker capture cases | Separate author evidence, not an additional independent 71-test run. Parent integration acceptance remains pending. |
| Independent runtime integration suite | **8 passed**, 5.64 s | Real headless ranking replay, quiet Sleeper pick sync, constructor, capture, SQL artifact, dependency receipt and fresh equivalent-session adoption. Synthetic network-denied inputs only. |
| Independent local read guard suite | **32 passed**, in a 39-case combined run lasting 3.58 s | Combined with the seven-case predecessor of the runtime review. This is observed local-source safety, not provider-change detection or a latency benchmark. |

Lane B source freeze: `prepared_trade_cohort.py` SHA-256
`393ac552eef1e262591e3a3f6e00f6154f90f1fd8cd594cda80aa52a91771375`;
tests `cb1916e7bb72084cf51e346f66d0827a1da6fda72d607fe5875537eb75e2a4f0`.
Payload independently reviewed at source `13e9b8548695c8dcd0935f5f45770c51a5f5e6e0094c78ddc57b7d173b3078f5`.
These are lane snapshots, not a final whole-release source manifest.
Independent runtime review tests are frozen at
`6a20ab2bf8ca1538c038e3a4f653221e7d50ac7c4e5452cbce67be41b945915d`.

Named behavioral RED→GREEN controls before their repairs:

- `test_espn_fresh_owner_contradiction_revokes_retained_private_binding` and
  `test_missing_espn_roster_envelope_is_failure_not_valid_empty`: both initially failed.
- Fresh Sleeper `/users` projection: `test_quiet_sleeper_adapter_reads_only_known_league_and_keeps_fresh_pick_evidence`
  and the `/users=None` failure case initially failed; real display-name projection then passed.
- `test_imported_opponent_ids_preserve_existing_platform_member_namespace` and
  `test_fleaflicker_fallback_and_opponent_actor_exclusion_use_flea_prefix`: both initially failed.
  Final identity matches existing `espn:<owner identifier>` / `flea:<league>.t<team>` conventions.
- `test_null_saved_scoring_uses_documented_native_default_not_skip`: initially failed;
  NULL now follows the existing 1QB PPR default, explicitly labeled `native_default`.
- `test_only_inactive_roster_assignment_changes_source_identity` (reserve/taxi)
  and `test_legacy_normalized_source_missing_availability_remains_explicit_unknown`:
  all three initially failed. Source receipts now distinguish an IR/taxi-only
  change from unchanged player ownership, without upgrading missing availability
  evidence to an observed empty list.

Cross-review also requested post-restore card/public mutation rejection and uniform
oversized-number failure in the payload codec; Lane C repaired both before the
independent 68-case run. No pricing/evaluation was added to restore.

Code-walk anchors at this local snapshot:

- [Cohort resolver](../../../backend/prepared_trade_cohort.py#L130) and
  [quiet source adapters](../../../backend/prepared_trade_cohort.py#L274): detached
  reader inputs, recognized app identities, fresh exact team binding, no session/DB writers.
- [Capture sink](../../../backend/prepared_trade_payload.py#L347) and
  [complete restore](../../../backend/prepared_trade_payload.py#L504): preparation
  callbacks assemble evidence without persistence; restore checks complete dependencies.
- [Inventory batches](../../../backend/prepared_trade_payload.py#L420): immutable
  baseline checks and exact ordered subsequences; commit remains the caller's responsibility.
- [Durable save](../../../backend/prepared_trade_store.py#L403),
  [adoption writer](../../../backend/prepared_trade_store.py#L796), and
  [participant deletion](../../../backend/prepared_trade_store.py#L921): separate
  prepare/publication lifecycles and account-data fencing. Parent final tests qualify integration.

## Historical v1 integration review and required final proof

Review identified source clocks fixed at sweep start, synchronization timestamps
invalidating identical pick inputs, incomplete model-file identity, and deferred
suppression mutations needing real-publication application. Parent/store integration
is addressing these with callable clocks, semantic receipts, implementation binding
and transactional adoption. The independent runtime suite verifies exact unchanged
source reuse without renewing original expiry, all-participant leases before pick
sync, dark-sync/deleted-claim refusal, board or IR-only source changes rejecting
completed generation, persisted cohort recovery after an expired claim, and waiting
for deferred work. Its final case prepares a real full inventory, rebuilds an
equivalent fresh session, compares the actual receipt, and adopts all cards in
order with durable impressions and no synthetic decisions/activity. No receipt or
read guard is mocked in that case. Final-source coverage beyond these bounded
checks remains the parent's acceptance responsibility.

Before release, the parent must record exact-head results for storage, account
deletion, retry/lease/stop races, actual prepare→restart→adopt behavior, identical
full inventory/order/proof/decision metadata, no preparation exposure/activity or
notifications, time-bound source/disposition expiry, failure-before-publication,
and zero changes to model settings or offer limits. An unexpired artifact is not
proof its dependencies are current. MFL must consume the verified fresh future-pick
snapshot; ESPN/Fleaflicker retain their existing user-asserted pick authority.

## Pending acceptance and release evidence

- Parent complete focused/backend suite and independent final integration review.
- Exact-head hosted CI, current mobile structural/unit/testID/TypeScript checks and web tests.
- Fresh versus prepared first-durable and full-completion timings, including a large
  inventory and peak memory; no cache-hit performance claim from unit tests.
- Reviewed PR/merge, exact deployed commit, authenticated configuration readback,
  canary and initial full-cohort coverage with skips/errors kept in the denominator.
- Physical-device TestFlight checks below. No simulator or Maestro work is required.

Manual checklist: open each supported linked league (including coowned and account-only);
tap Find and verify the first tile is actionable and later cards continue; change
rankings/outlook/fairness/roster and verify stale inventory is withheld; restart the
server and verify only current artifacts reuse; confirm no unsolicited inbox/push,
likes or proposals. Measure tap→actionable first tile separately from background
generation. **The three-second product goal and production coverage are unverified.**

## Independent chunked-cache review — 2026-09-23

These are scoped review results for the v2 worktree, not a new production or
device-performance claim. The parent owns final-source full/hosted suites,
serialized constructor benchmarks and release authorization.

- Before the final feedback/corruption repairs, the independent B group plus
  five parent runtime controls passed **42 cases in 16.20 s**. Coverage included
  actual telemetry-enabled preparation/adoption, original proof/evidence and
  retry identity, complete SQL bind-value byte accounting, graph amplification
  and cached-depth checks, exact admission binding, late-page corruption,
  participant deletion/export privacy, seal rollback and crash-prefix recovery.
  This historical run does not cover the subsequently added controls below.
- The final eight-case B actual-runtime group passed within a combined run:
  first-prefix real like/pass continuation, direct-SQL partner board/outlook
  revocation without local epoch notification, exact corrupt-inventory retirement
  after a valid prefix, transient writer retry and telemetry parity. The separate
  current-disposition callback miss→unchanged artifact→successful retry case
  passed **1 case in 3.79 s**. No constructor, receipt or durable evidence writer
  is mocked in these integration controls; the callback-specific case injects
  only the read-time eligibility result.
- The active-input receipt contract passed **10 cases in 1.23 s**: recognized trade
  feedback may change while full admission remains strict; explicit or unknown
  swipe inputs and persisted partner board/outlook/asset or own tier edits remain
  invalidating. A separate read-only agent review confirmed the split against
  actual ranking feedback code. Default full-admission fields and semantics are
  retained, not replaced by the active receipt.
- Real matched-like continuation and an explicit board edit between active
  capture and full admission passed independently, **2 cases in 5.14 s**. The final
  roster-during-index race control then passed in the parent's frozen-source
  feedback/runtime group, **13 cases in 7.07 s**. That group includes the three B
  feedback tests; it is not an additional independent thirteen-case run.
- The storage author ran the final revised store plus B retirement/attestation
  controls on both isolated SQLite (**59 cases in 8.25 s**) and a disposable
  local PostgreSQL schema (**59 cases in 14.54 s**). Those are author-run results,
  separate from B's earlier independent seven-case PostgreSQL run. No production
  database was used, and no current PostgreSQL run is inferred from SQL compilation.

Named behavioral failures witnessed before repair:

- A real first-prefix `like` and `pass` each wrote the valid action but changed
  the full receipt, causing the prepared job to error and revoke unrelated cards.
  The active-input split now preserves continuation while explicit source edits
  still revoke it. A like creating an actual pending mutual match is also covered.
- A corrupt late card page left a valid first 30 prefix but remained sealed and
  active. Exact ID/root retirement now prevents the next request from hitting
  that corrupt artifact; original prefix/evidence remains, a newer replacement
  cannot be retired by the old root, and transient writer failures remain retryable.
- A direct SQL league-member roster change during index admission was accepted
  as the later read guard's baseline and the job completed. Capturing the original
  read guard before admission now yields `inputs_changed` before any impressions
  or cards publish. This was an actual admission path, not only a hash-unit test.

The first three failures above were observed together as **3 failing cases
in 9.21 s** (like, pass, corrupt retirement); the roster race separately failed
**1 case in 3.73 s** before the parent's guard-capture move. Review controls retain
original proof strings and durable history, never reprice cards or impose an
offer cap. Candidate singleton/SQL ceilings remain explicit fail-closed resource
bounds: passing the small telemetry-on case is not evidence that every cohort's
candidate singleton fits. Read-time local safety cannot detect an unobserved
provider change. Final capacity, memory, first-action latency and all-team readiness
must be reported from their own qualification/rollout evidence.

Final compatibility follow-up found that the new prepared awaiting/matched R4
projection ignored the existing `trade.presentment_rules` kill switch. Two
actual flag-OFF controls reproduced the mismatch: an eight-day awaiting like and
a pending match survived fresh Bilateral2 generation and exact full-receipt
comparison, but cache admission rejected them. The parent gated only the new
R4 projection on the same flag; independent exact-pass/source-like safety stays
active. Positive R4 and matched-like controls now explicitly pin the flag ON.
The final compatibility/feedback/runtime group passed **19 cases in 17.45 s**,
including both actual flag-OFF inventories, flag-ON matched-like continuation,
disabled-history-read controls and the admission input races. No runtime/test
edits followed that freeze from Lane B. Earlier dense benchmark flags must be
reported as measured; they are not implied to match current production settings.
