# Validation — persistent prepared trade inventory

2026-09-22. Local implementation evidence, not deployment or activation evidence.
Baseline: `ff122752`; release owner remains the parent agent. See [scope](scope.md).

## Executed lane evidence

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

## Integration review and required final proof

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
