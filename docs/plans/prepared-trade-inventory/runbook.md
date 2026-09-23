# Runbook — silent prepared trade inventory

Implementation runbook; follow [release evidence](release.md) for current rollout state.
Use [validation](validation.md) and [status](status.md), not this procedure, as evidence.
The approved [chunked-storage revision](chunked-storage-plan.md) is implemented
locally, not yet release-qualified. Production caching remains OFF after the second
failed canary; the v2 procedure below is not a deployment or successful-canary receipt.

## Preconditions

Use only the reviewed exact release head after full/hosted verification. Keep the
existing exclusive Bilateral revision 2 selection and all fairness/offer settings
unchanged. The capability is `trade.prepared_inventory`; actual preparation and
adoption require numeric `prepared_trade_inventory_enabled=1` (default 0).
Use the existing audited admin-config workflow and authenticated readback, never a
direct database knob update. There is no new infrastructure or paid-provider setup.

The cohort is verified existing app identities and already known current-season
linked leagues. It is independent of 30-day activity. Imported opponents are not
new app users. Sleeper coowners retain separate personal inventories and one canonical
team; imported platforms require an unambiguous retained/verified team binding.
Missing binding/authentication, unavailable source, unsupported format and valid
empty leagues are distinct outcomes. A resolved target is not a ready artifact.

## Operator sequence

All operations use existing `X-Cron-Secret` authorization. Keep its value in the
existing secure credential mechanism, never a committed command or report.

1. `POST /api/admin/prepared-trades` with a new nonempty `idempotency_key` and
   `dry_run:true`. Optional `user_id` / `league_id` restrict a canary. Discovery
   performs fresh read-only provider requests; it is not a zero-load operation.
   It does not import leagues, write shown offers or notify users.
2. Inspect cohort aggregate reasons and `discovery_complete`. Save sanitized
   coverage separately from resolved-target counts. A source failure can leave
   membership unresolved; do not invent a count of successfully cached teams.
3. After approved activation/readback, submit a small scoped non-dry-run canary.
   Poll `GET /api/admin/prepared-trades`; once assigned, use `?sweep_id=<id>` for
   durable progress. POST is asynchronous; its response does not mean preparation
   completed. Reusing an idempotency key requires the same frozen target cohort.
4. Verify ordinary Find adopts only the exact user/team/format/fairness/input
   scope, with evidence committed before each public batch. Verify an input change
   falls back to ordinary fresh generation, without repricing old likes or proofs.
5. Run the authorized unscoped all-user sweep. Record target states, unresolved
   cohort reasons, unexpired artifacts, and separately observed current-source
   validation. Do not relabel `unexpired_artifacts` as fresh-ready coverage.
6. Check silent maintenance refresh/resume after restart on the final release.
   The scheduler resumes unfinished durable sweeps before creating a new hourly
   cohort; delayed retry availability does not mean a sweep is complete.
   Work is sequential and defers admission while interactive work runs; it is
   cooperative priority, not hard CPU preemption of a running constructor.

## Storage, validation and recovery

New preparation uses v2 staging manifests, ordered card/evidence/compact-admission
pages and the original scoped diagnostic nodes. Staging is not adoptable. The
store freezes the complete root before validating all records and dependencies,
then checks that same root and mints a reserved, versioned semantic attestation.
Only successful sealing atomically replaces the active scope pointer; failure
leaves the previous valid artifact in place. Empty results are real sealed
inventories, not failures. No offer cap, ranking change or proof reconstruction
is introduced.

The current transport limits are 4 MiB logical / 768 KiB encoded per page, at most
100 records per page, and a conservative 2 MiB budget for each complete SQL
execution, including all bound parameters. Capture normally targets about 1 MiB
pages. Writes split by bytes as well as row count. Individual records, metadata,
diagnostic closures and expanded graphs are separately bounded before copying or
expansion; an oversized indivisible record fails, never truncates the inventory.
Candidate-set JSON retains its original singleton format and must fit both its
codec limit and the actual uncompressed SQL statement budget. Do not raise these
bounds to conceal an oversize failure. The old v1 64 MiB logical / 2 MiB encoded
whole-envelope limits remain unchanged for existing v1 artifacts; they are not
v2 whole-inventory limits.

Admission requires the recognized store-minted attestation bound to the validated
root, original metadata/header, counts and validator identity. Missing or unknown
attestation is a miss, not an inferred pass. It scans every root-authenticated
compact disposition entry and checks current inputs; it does not rehydrate every
native proof. Each publishing batch still restores full native proofs, checks
exact admission correspondence and original diagnostic/evidence dependencies,
then re-reads the authoritative original slice before commitment. Evidence must
commit before checkpointing and exposing cards. A corrupt late page can leave an
earlier independently valid prefix, but the affected batch must never publish;
do not mix a fresh-generation suffix after commitment. Missing trailing real or
ghost evidence must report incomplete adoption, never successful short completion.
The first batch targets 30 real cards, subsequent batches at most 100, with
smaller byte-bound batches allowed. Ghost evidence has its own durable cursor and
bounded suffix batches; real-card completion alone is not full adoption completion.

Every new adoption must match the full current dependency receipt. Once admitted,
each batch instead fences explicit ranking/board/preferences and source/model
inputs; ordinary like/pass feedback does not freeze computed Elo or action history.
Current exact passes, source-like validity and awaiting/matched packages are
projected before publication and on reads. Verify that an early like/pass removes
affected offers while unrelated original offers continue, with no repricing or
fresh suffix. Unknown swipe types remain conservative input changes. A current
history mismatch/unavailable history is not stored corruption: do not retire a
valid inventory for it. Typed artifact failures retire only the exact failed
inventory/root; transient database failures do not authorize retirement.

Storage/validation work renews only its still-live generation or adoption token;
it cannot revive an expired, replaced, stopped or deleted claim. An expired
adoption lease can be claimed again under a new token, retaining the original
publication timestamp and exact evidence IDs. Evidence committed before a crash
but not checkpointed is recovered by exact-content retry. Interrupted unsealed
work may be regenerated, never adopted. V1 and v2 coexist: new generation writes
v2, while the existing v1 adoption path remains available when no v2 inventory is
selected. Neither path silently rewrites old proofs or behavioral history.

The five-minute in-memory cleanup tick has a scoped timer boundary. Private
preparation follows its live 300-second persistent generation claim and bounded
same-token renewals, not the unrelated 60-second interactive total-age timeout.
For v2 interactive adoption, only a successfully durable batch/checkpoint resets
the 60-second stall timer; polling or reading does not. Ordinary generation keeps
its existing timeout. No timer extends original artifact, card or read-guard expiry.

Artifacts last at most 24 hours; lease renewal, reading and adoption never extend
the original artifact or native-card expiry. Adopted memory jobs retain the
existing 30-minute bound. Bounded transport is not bounded total process memory:
the unchanged constructor can retain its full native inventory, and the existing
job/service retains cumulative published cards. The current owner logger supplies
at most 100 rows per capture callback, but its pre-compaction callback graph has no
separate aggregate-byte cap; transport page size is not its peak-memory bound.
Full seal validation and admission checks have real CPU and I/O cost. Measure
complete preparation, first durable batch, full adoption and peak RSS separately;
no three-second or existing-tier capacity guarantee follows from page sizes.
The revised local telemetry-ON 936-offer check completed every original offer:
first 30 durable in 1.08137s, full adoption in 22.1519s. This is not a phone or
production three-second result, nor a dense-load capacity guarantee. See the
[qualification measurements](validation.md) for phase/resource limits and the
non-identical telemetry setting of the earlier comparison.

Scoring uses the saved league format; database NULL means the existing native
`1qb_ppr` default and is labeled as such. Preparation uses the latest observed
in-memory fairness setting when available, otherwise the native 0.5 default;
a different actual request must miss. This is not a claim that every client's
locally stored setting has been synchronized to the backend.

## Failure and rollback

Provider credentials stay in existing secure readers. Do not invoke reconnect
notifications or the unrelated daily/weekly notification tick to warm inventory.
Refresh source/pick data only through the known-league quiet path. Source failures
must not overwrite an authoritative ledger with an invented empty response.
Fleaflicker's source does not attest a season; ESPN/Fleaflicker do not provide the
owned-pick ledger. Retained platform/user assertions keep their declared authority,
never become stronger provider evidence merely because preparation ran.

To stop one sweep: `DELETE /api/admin/prepared-trades` with its `sweep_id`. This
revokes outstanding preparation claims and retains already durable records; it is
not the global adoption kill switch. For global rollback, set
`prepared_trade_inventory_enabled=0` through the audited config endpoint and read
back the result. Ordinary fresh generation remains available. Do not delete
historical likes/matches/impressions or change another model knob. Re-enable only
after the failed invariant and final regression evidence have been reviewed.

Account deletion fences/removes v2 staging, validating, sealed and retired
inventories for every consumed participant, including their pages, nodes and
participant indexes. Pruning also handles expired, retired and abandoned stages.
Hourly private retention cleanup continues while caching is OFF, without provider
discovery, refresh or new preparation. The 24-hour retention bound controls
eligibility; physical removal occurs on the next successful maintenance pass,
not at an exact expiry-time deadline.
Account exports contain allowed manifest metadata only, not page/node payloads,
source receipts, recovery metadata or lease tokens; existing impression exports
still remove the private `prepared_runtime` recovery field.

Turning caching OFF is the operational rollback. A binary downgrade to code that
predates v2 is different: that binary does not know the new private tables and
cannot honor their deletion obligations. Before such a downgrade, require a
reviewed, verified v2 purge or a deletion-compatible bridge release. Disabling
the flag alone does not make an old binary safe for retained v2 data.

No live operation, production ready count, or physical-device latency is established
by this document. Parent owns the release receipt and initial production sweep.
